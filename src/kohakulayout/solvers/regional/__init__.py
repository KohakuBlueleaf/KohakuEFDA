"""Regional construction followed by greedy shrinking."""

from typing import Any

from kohakulayout.errors import SolverError
from kohakulayout.solvers.base import BaseSolver
from kohakulayout.solvers.baseline.shrink import Shrink
from kohakulayout.solvers.protocol import Param
from kohakulayout.solvers.regional.candidates import Proposals
from kohakulayout.solvers.regional.search import DEFAULTS, Search
from kohakulayout.solvers.registry import register

POSITIVE = (
    "attempts",
    "candidates",
    "gap_cycle",
    "restart_cycle",
    "radius_cycle",
    "neighbor_cycle",
    "expand_cycle",
)
PROBABILITIES = ("repair_threshold", "pressure_decay", "replace_equal")


def _param(name: str, value: Any) -> Param:
    kind = "int" if isinstance(value, int) else "float"
    return Param(name=name, type=kind, default=value)


@register
class Regional(BaseSolver):
    """Regional construction then shrinking; a project's solver subclasses it with its own ``search``."""

    id = "regional"
    resume = "continues"
    search: type = Search
    params = (
        *(_param(k, v) for k, v in DEFAULTS.items()),
        Param(name="shrink_rounds", type="int", default=200),
    )

    def construct(self, ctx: Any) -> None:
        for key in POSITIVE:
            if self.opts[key] < 1:
                raise SolverError(f"{key} must be positive")
        for key in PROBABILITIES:
            if not 0 <= self.opts[key] <= 1:
                raise SolverError(f"{key} must be between zero and one")
        if (
            len(ctx.world.placements) == len(ctx.world.netlist.cells)
            and not ctx.world.unrouted()
        ):
            return
        self.search(ctx, {k: self.opts[k] for k in self.search.defaults}).run()

    def improve(self, ctx: Any) -> None:
        if ctx.world.unrouted() or len(ctx.world.placements) != len(
            ctx.world.netlist.cells
        ):
            return
        Shrink(ctx, self.opts["shrink_rounds"]).run()


__all__ = ["DEFAULTS", "Proposals", "Regional", "Search"]
