"""The context a solver runs in: problem, physics, world, budget, rng, plugins, progress, the best archive.

The engine gives a solver everything a search needs and owns nothing about how to search.
"""

import random
import time
from collections.abc import Callable, Iterable
from fractions import Fraction
from typing import Any

from kohakulayout.engine.assessment import assess, metrics
from kohakulayout.engine.attempt import Attempt, Block, Result
from kohakulayout.engine.budget import Budget
from kohakulayout.engine.builder import Builder
from kohakulayout.engine.checkpoint import (
    Checkpoint,
    rng_state_jsonable,
    rng_state_native,
)
from kohakulayout.engine.execution import InProcess
from kohakulayout.engine.plugins import DROP, PluginManager, default_plugins
from kohakulayout.engine.progress import Event, NullSink
from kohakulayout.engine.scopes import Scope
from kohakulayout.ir import Assessment, Frame, Layout, Problem, Refusal
from kohakulayout.physics import get
from kohakulayout.physics.objective import energy
from kohakulayout.state import Token, World, make_router


class Context:
    def __init__(
        self,
        problem: Problem,
        physics: Any = None,
        seed: int = 0,
        kernel: str = "python",
        router: Any = "default",
        checker: Any = None,
        budget: Budget | None = None,
        plugins: Iterable[Any] | None = None,
        progress: Any = None,
        run: str | None = None,
        execution: Any = None,
    ) -> None:
        self.problem = problem
        self.physics = physics if physics is not None else get(problem.physics)
        self.seed = seed
        self.rng = random.Random(seed)
        if isinstance(router, str):
            router = make_router(router)
        self.world = World(problem, self.physics, kernel=kernel, router=router)
        if checker is not None:
            checker.mount(self.world)
        self.budget = budget if budget is not None else Budget()
        self.plugins = PluginManager(
            tuple(plugins) if plugins is not None else default_plugins()
        )
        self.progress = progress if progress is not None else NullSink()
        self.run = run if run is not None else f"run-{seed}"
        self.execution = execution if execution is not None else InProcess()
        self.seq = 0
        self.phase = ""
        self.solver = ""
        self.params: dict[str, Any] = {}
        self.attempts = 0
        self.accepts = 0
        self.refusals: list[Refusal] = []
        self.best: Token | None = None
        self.best_assessment: Assessment | None = None
        self.checkpoints: list[Checkpoint] = []
        self._builder: Builder | None = None

    # -------------------------------------------------------------- doors
    def builder(self) -> Builder:
        if self._builder is None or self._builder.world is not self.world:
            self._builder = Builder(self)
        return self._builder

    def emit(self, kind: str, payload: Any) -> Event:
        self.seq += 1
        event = Event(
            kind=kind, run=self.run, seq=self.seq, at=time.time(), payload=payload
        )
        self.progress.emit(event)
        return event

    def log(self, message: str, **attrs: Any) -> None:
        self.emit("log", {"message": message, **attrs})

    def refused(self, refusal: Refusal) -> None:
        self.refusals.append(refusal)
        self.emit("refusal", refusal)

    # ----------------------------------------------------------- attempts
    def attempt(
        self, fn: Callable[[Builder], Any], label: str = "attempt", cost: int = 0
    ) -> Result:
        """Run ``fn`` on the builder inside a transaction; a returned refusal rolls it back."""
        attempt = Attempt(label=label, fn=fn, cost=cost)
        world = self.world
        before = world.seq
        try:
            attempt = self.plugins.transform("pre_attempt", self, attempt)
        except Block as blocked:
            result = Result(
                attempt=attempt,
                refusal=blocked.refusal,
                value=None,
                before=before,
                after=before,
                charged=0,
            )
            self.refused(blocked.refusal)
            return result
        builder = self.builder()
        builder.last = None
        charged = self.budget.used
        with world.transaction() as tx:
            value = attempt.fn(builder)
            refusal = value if isinstance(value, Refusal) else builder.last
            if refusal is None:
                tx.commit()
        if isinstance(value, Refusal) and value is not builder.last:
            self.refused(value)
        self.attempts += 1
        result = Result(
            attempt=attempt,
            refusal=refusal,
            value=None if isinstance(value, Refusal) else value,
            before=before,
            after=world.seq,
            charged=self.budget.used - charged,
        )
        return self.plugins.transform("post_attempt", self, result, attempt)

    # ----------------------------------------------------------- archive
    def snapshot(self) -> Token:
        return self.world.snapshot()

    def restore(self, token: Token) -> None:
        self.world.restore(token)

    def assess(self, layout: Layout | None = None) -> Assessment:
        """L1 for the world's state, through the screens and the cache the plugins keep."""
        values = metrics(self.world)
        digest = self.world.digest()
        found = self.plugins.first("pre_assess", self, digest, values)
        if isinstance(found, Assessment):
            return found
        assessment = assess(self.world, layout)
        out = self.plugins.transform("post_assess", self, assessment)
        return out if isinstance(out, Assessment) else assessment

    def screened(self) -> bool:
        """Whether the plugins veto assessing the current state."""
        values = metrics(self.world)
        return (
            self.plugins.first("pre_assess", self, self.world.digest(), values) is False
        )

    @staticmethod
    def rank(assessment: Assessment, objective: Any) -> tuple[int, int, int, Fraction]:
        """Valid first, then complete, then the fewest gaps, then the objective's energy."""
        gaps = int(assessment.metrics.get("missing", 0)) + int(
            assessment.metrics.get("unrouted", 0)
        )
        return (
            0 if assessment.valid else 1,
            0 if assessment.complete else 1,
            gaps,
            energy(objective, assessment.metrics),
        )

    def consider(
        self, token: Token | None = None, key: Callable[[Assessment], Any] | None = None
    ) -> Assessment | None:
        """Assess the current state and keep it as best when it ranks better; None when screened or vetoed."""
        if self.screened():
            return None
        assessment = self.assess()
        rank = (
            key if key is not None else (lambda a: self.rank(a, self.physics.objective))
        )
        if self.best_assessment is not None and rank(assessment) >= rank(
            self.best_assessment
        ):
            return assessment
        return self.accept(token, assessment)

    def accept(
        self, token: Token | None = None, assessment: Assessment | None = None
    ) -> Assessment | None:
        """Make the current state the best, unless a plugin vetoes."""
        token = token if token is not None else self.snapshot()
        assessment = assessment if assessment is not None else self.assess()
        if self.plugins.first("pre_accept", self, token, assessment) is False:
            return None
        self.best, self.best_assessment = token, assessment
        self.accepts += 1
        self.emit("assessment", assessment)
        self.plugins.notify("post_accept", self, token, assessment)
        return assessment

    def discard(self, token: Token) -> None:
        return None

    def restore_best(self) -> bool:
        if self.best is None:
            return False
        self.restore(self.best)
        return True

    # ------------------------------------------------------------- frames
    def frame(self, phase: str | None = None, layout: bool = False) -> Frame | None:
        frame = Frame(
            run=self.run,
            seq=self.seq + 1,
            at=time.time(),
            phase=phase if phase is not None else self.phase,
            metrics=metrics(self.world),
            layout=self.world.freeze() if layout else None,
        )
        out = self.plugins.transform("on_frame", self, frame)
        if out is DROP:
            return None
        self.emit("frame", out)
        return out

    def checkpoint(self) -> Checkpoint:
        checkpoint = Checkpoint(
            run=self.run,
            seq=self.seq + 1,
            solver=self.solver,
            params=self.params,
            seed=self.seed,
            rng_state=rng_state_jsonable(self.rng.getstate()),
            budget=self.budget.snapshot(),
            phase=self.phase,
            layout=self.world.freeze(),
            best=(
                self.world.freeze()
                if self.best is None
                else Layout(
                    problem=self.problem.digest(),
                    placements=self.best.placements,
                    wires=self.best.wires,
                    units=self.best.units,
                    reservations=self.best.reservations,
                )
            ),
            best_metrics=(
                dict(self.best_assessment.metrics)
                if self.best_assessment is not None
                else {}
            ),
            attempts=self.attempts,
            accepts=self.accepts,
        )
        self.plugins.notify("on_checkpoint", self, checkpoint)
        self.checkpoints.append(checkpoint)
        self.emit("checkpoint", checkpoint)
        return checkpoint

    def resume(self, checkpoint: Checkpoint) -> None:
        """Continue from a checkpoint: the world, the rng, the budget's spend and the best."""
        self.world.load(checkpoint.layout)
        self.rng.setstate(rng_state_native(checkpoint.rng_state))
        self.budget.used = int(checkpoint.budget.get("used", 0))
        self.solver, self.params = checkpoint.solver, dict(checkpoint.params)
        self.attempts, self.accepts = checkpoint.attempts, checkpoint.accepts
        if checkpoint.best is not None:
            current = self.world.freeze()
            self.world.load(checkpoint.best)
            self.best, self.best_assessment = self.world.snapshot(), self.assess()
            self.world.load(current)
        self.log("resumed", seq=checkpoint.seq)

    # --------------------------------------------------------- execution
    def gather(self, tasks: Iterable[Any]) -> list[Any]:
        return self.execution.gather(tasks)

    def scope(self, component: str, units: int | None = None) -> Scope:
        return Scope(self, component, units)

    def layout(self) -> Layout:
        return self.world.freeze()

    def best_layout(self) -> Layout:
        if self.best is None:
            return self.layout()
        return Layout(
            problem=self.problem.digest(),
            placements=self.best.placements,
            wires=self.best.wires,
            units=self.best.units,
            reservations=self.best.reservations,
        )


__all__ = ["Context"]
