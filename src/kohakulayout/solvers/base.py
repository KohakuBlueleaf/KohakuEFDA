"""``BaseSolver``: construct, then improve, inside the engine's loop of budget, frames and the best archive."""

from typing import Any

from kohakulayout.errors import BudgetExhausted
from kohakulayout.ir import Refusal
from kohakulayout.solvers.params import resolve
from kohakulayout.solvers.protocol import Outcome, Param


class BaseSolver:
    """Subclass, set ``id`` and ``params``, fill ``construct`` and ``improve``; ``run`` is the framework's.

    ``resume`` is ``"exact"`` when a resumed run reaches the same layout as an uninterrupted one
    (the future depends on the world, the rng state and the budget alone) and ``"continues"``
    when a resumed run only promises to finish.
    """

    id: str = "base"
    params: tuple[Param, ...] = ()
    resume: str = "exact"

    def __init__(self) -> None:
        self.opts: dict[str, Any] = {}
        self.refusals: list[Refusal] = []
        self.exhausted: str | None = None

    def construct(self, ctx: Any) -> None:
        return None

    def improve(self, ctx: Any) -> None:
        return None

    def outcome(self, ctx: Any) -> Outcome:
        best = ctx.best_assessment
        if best is not None:
            return "complete" if best.complete else "incomplete"
        world = ctx.world
        placed = len(world.placements) == len(world.netlist.cells)
        routed = len(world.wires) == len(world.netlist.nets)
        return "complete" if placed and routed else "incomplete"

    def run(self, ctx: Any, **params: Any) -> Outcome:
        self.opts = resolve(self.params, params)
        self.refusals = ctx.refusals
        self.exhausted = None
        ctx.solver, ctx.params = self.id, dict(self.opts)
        ctx.frame("start")
        try:
            with ctx.scope("construct"):
                self.construct(ctx)
            ctx.frame("constructed", layout=True)
            ctx.consider()
            with ctx.scope("improve"):
                self.improve(ctx)
        except BudgetExhausted as exc:
            self.exhausted = str(exc)
            ctx.log(self.exhausted, phase=ctx.phase)
        ctx.consider()
        if ctx.best is not None and ctx.world.digest() != ctx.best.digest:
            ctx.restore_best()
        ctx.frame("end", layout=True)
        return self.outcome(ctx)


__all__ = ["BaseSolver"]
