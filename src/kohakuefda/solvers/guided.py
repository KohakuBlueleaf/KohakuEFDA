"""``endfield.guided``: a lines or regional seed, then the framework's local search
repaired through contact proposals, with batch relocations, depot reseating and adaptive
operator selection."""

from typing import Any

from kohakuefda.solvers.lines import lines_seed
from kohakuefda.solvers.search import DEFAULTS, GUIDED, EndfieldSearch, GuidedSearch
from kohakulayout.solvers.local.climb import PARAMS, LocalSolver, complete
from kohakulayout.solvers.local.search import Trajectory
from kohakulayout.solvers.protocol import Param
from kohakulayout.solvers.registry import register

LOCAL = frozenset(p.name for p in PARAMS)
REGIONAL_SEED = {k: DEFAULTS[k] for k in ("candidates", "extent_weight")}
OVERRIDES: dict[str, Any] = {
    **GUIDED,
    "repack_gap": 0,
    "repack_every": 8,
    "repack_size": 5,
    "repack_candidates": 40,
    "reseat_every": 12,
    "batch_moves": True,
    "adaptive_moves": True,
}


@register
class GuidedLayout(LocalSolver):
    """Seed feasibly, then search free coordinates with contact repair."""

    id = "endfield.guided"
    search = GuidedSearch
    params = (
        *(
            p.model_copy(update={"default": OVERRIDES.get(p.name, p.default)})
            for p in PARAMS
        ),
        *(
            Param(name=k, type="int" if isinstance(v, int) else "float", default=v)
            for k, v in GUIDED.items()
            if k not in LOCAL
        ),
        Param(
            name="acceptance",
            type="choice",
            default="climb",
            choices=("climb", "anneal"),
        ),
        Param(
            name="seed_kind",
            type="choice",
            default="lines",
            choices=("lines", "regional"),
            doc="the lines shape, falling back to regional construction when it does not land",
        ),
        Param(name="seed_gap", type="int", default=2, doc="regional seed clearance"),
        Param(
            name="seed_units",
            type="int",
            default=1024,
            doc="actions the lines seed may spend",
        ),
    )

    def construct(self, ctx: Any) -> None:
        self.validate()
        self.method = self.opts["acceptance"]
        if self.opts["seed_kind"] == "lines" and lines_seed(
            ctx, self.opts["seed_units"]
        ):
            return

        seed = {**self.opts, **REGIONAL_SEED, "gap": self.opts["seed_gap"]}
        Trajectory(ctx, seed, "climb", EndfieldSearch).construct()

    def improve(self, ctx: Any) -> None:
        if complete(ctx.world):
            Trajectory(ctx, self.opts, self.method, self.search).improve()


__all__ = ["OVERRIDES", "REGIONAL_SEED", "GuidedLayout"]
