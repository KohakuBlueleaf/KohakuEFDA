"""Level 3: is a solver a legal client of the engine? Budget, frames, reproducibility, resume, the toys."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from kohakulayout.engine import Budget, Context, ListSink
from kohakulayout.engine.plugins import CheckpointPlugin, default_plugins
from kohakulayout.ir import Problem
from kohakulayout.solvers.registry import get
from kohakulayout.state import StateCheck

ToyBuilder = Callable[[], Problem]


@dataclass
class Report:
    solver: str
    checks: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures

    def note(self, check: str, ok: bool, detail: str = "") -> None:
        self.checks.append(check)
        if not ok:
            self.failures.append(f"{check}: {detail}" if detail else check)


def _run(
    solver_id: str,
    problem: Problem,
    seed: int,
    units: int | None,
    params: dict[str, Any],
    plugins: Any = None,
) -> tuple[Context, str, ListSink]:
    sink = ListSink()
    ctx = Context(
        problem,
        seed=seed,
        budget=Budget(units=units),
        progress=sink,
        checker=StateCheck(),
        plugins=plugins,
    )
    outcome = get(solver_id).run(ctx, **params)
    return ctx, outcome, sink


def level3(
    solver_id: str,
    toys: dict[str, ToyBuilder],
    params: dict[str, Any] | None = None,
    units: int = 5000,
    seed: int = 7,
) -> Report:
    """Every obligation on the solver protocol against each toy problem; failures name the toy."""
    params = params or {}
    report = Report(solver=solver_id)
    for name, build in toys.items():
        ctx, outcome, sink = _run(solver_id, build(), seed, units, params)
        report.note(f"{name}: completes", outcome == "complete", f"outcome {outcome}")
        report.note(
            f"{name}: best is valid",
            ctx.best_assessment is not None and ctx.best_assessment.valid,
        )
        frames = sink.of("frame")
        phases = [f.payload.phase for f in frames]
        report.note(
            f"{name}: frames start and end",
            bool(frames) and phases[0] == "start" and phases[-1] == "end",
            str(phases[:3]),
        )
        report.note(
            f"{name}: end frame carries a layout",
            frames[-1].payload.layout is not None if frames else False,
        )
        report.note(f"{name}: budget charged", ctx.budget.used > 0)
        again, _, sink2 = _run(solver_id, build(), seed, units, params)
        report.note(
            f"{name}: seed reproduces the layout",
            again.world.digest() == ctx.world.digest(),
        )
        report.note(
            f"{name}: seed reproduces the events", sink2.digest() == sink.digest()
        )
        tight = max(1, ctx.budget.used // 3)
        starved, starved_outcome, _ = _run(solver_id, build(), seed, tight, params)
        report.note(
            f"{name}: budget never exceeded by more than one charge",
            starved.budget.used <= tight + 1,
            f"used {starved.budget.used} of {tight}",
        )
        report.note(
            f"{name}: exhausted budget is incomplete, not failed",
            starved_outcome in ("incomplete", "complete"),
        )
        plugins = (*default_plugins(), CheckpointPlugin(every_accepts=1))
        first, _, _ = _run(solver_id, build(), seed, units, params, plugins)
        if first.checkpoints:
            checkpoint = first.checkpoints[0]
            resumed = Context(
                build(), seed=seed, budget=Budget(units=units), checker=StateCheck()
            )
            resumed.resume(checkpoint)
            resumed_outcome = get(solver_id).run(resumed, **params)
            if getattr(get(solver_id), "resume", "exact") == "exact":
                report.note(
                    f"{name}: resume reaches the same layout",
                    resumed.world.digest() == first.world.digest(),
                )
            else:
                report.note(
                    f"{name}: resume finishes",
                    resumed_outcome == "complete"
                    and resumed.best_assessment is not None
                    and resumed.best_assessment.valid,
                    f"outcome {resumed_outcome}",
                )
        else:
            report.note(f"{name}: a checkpoint was taken", False)
    return report


__all__ = ["Report", "ToyBuilder", "level3"]
