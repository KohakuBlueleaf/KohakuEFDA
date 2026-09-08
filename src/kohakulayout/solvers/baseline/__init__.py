"""The baseline: a first-complete spread, then greedy shrinking."""

from typing import Any

from kohakulayout.errors import SolverError
from kohakulayout.solvers.base import BaseSolver
from kohakulayout.solvers.baseline.parallel import build_parallel
from kohakulayout.solvers.baseline.shrink import Shrink
from kohakulayout.solvers.baseline.spread import Spread
from kohakulayout.solvers.protocol import Param
from kohakulayout.solvers.registry import register


@register
class Baseline(BaseSolver):
    id = "baseline"
    resume = "continues"
    params = (
        Param(
            name="spread_attempts",
            type="int",
            default=256,
            doc="spread retries before giving up",
        ),
        Param(
            name="spread_slice",
            type="int",
            default=8,
            doc="attempts per worker slice when workers > 1",
        ),
        Param(name="spread_gap", type="int", default=0, doc="first lattice gap"),
        Param(name="spread_widest", type="int", default=6, doc="last lattice gap"),
        Param(
            name="shrink_rounds",
            type="int",
            default=200,
            doc="greedy compaction rounds",
        ),
        Param(
            name="flow_order",
            type="choice",
            default="bottom-up",
            choices=("bottom-up", "top-down"),
        ),
        Param(
            name="router",
            type="choice",
            default="default",
            choices=("default",),
            doc="router id for worker slices",
        ),
    )

    def construct(self, ctx: Any) -> None:
        opts = self.opts
        if opts["spread_widest"] < opts["spread_gap"]:
            raise SolverError("spread_widest cannot be below spread_gap")
        if opts["spread_attempts"] < 1 or opts["spread_slice"] < 1:
            raise SolverError("spread budgets must be positive")
        if (
            len(ctx.world.placements) == len(ctx.world.netlist.cells)
            and not ctx.world.unrouted()
        ):
            return
        if ctx.execution.workers > 1 and ctx.budget.units is None:
            build_parallel(ctx, opts, opts["router"])
        else:
            Spread(ctx, opts).run()

    def improve(self, ctx: Any) -> None:
        if ctx.world.unrouted() or len(ctx.world.placements) != len(
            ctx.world.netlist.cells
        ):
            return
        Shrink(ctx, self.opts["shrink_rounds"]).run()


__all__ = ["Baseline", "Shrink", "Spread", "build_parallel"]
