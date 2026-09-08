"""Hill climbing and simulated annealing: one trajectory, two acceptance rules."""

from typing import Any

from kohakulayout.errors import SolverError
from kohakulayout.solvers.base import BaseSolver
from kohakulayout.solvers.local.search import Trajectory
from kohakulayout.solvers.protocol import Param
from kohakulayout.solvers.registry import register

PARAMS: tuple[Param, ...] = (
    Param(
        name="construction_steps",
        type="int",
        default=128,
        doc="repair trials before giving up construction; 0 skips",
    ),
    Param(
        name="improvement_steps",
        type="int",
        default=2000,
        doc="move proposals; 0 stops at construction",
    ),
    Param(
        name="until_budget",
        type="bool",
        default=True,
        doc="with a budget, ignore the step caps and run until it ends",
    ),
    Param(
        name="candidates", type="int", default=150, doc="ranked anchors per insertion"
    ),
    Param(
        name="gap",
        type="int",
        default=2,
        doc="construction clearance around placed cells",
    ),
    Param(
        name="frontier_weight",
        type="float",
        default=0.0,
        doc="weight of the optimistic potential in construction energy",
    ),
    Param(
        name="local_repair_every",
        type="int",
        default=0,
        doc="0, or N: local repair on N-1 of every N steps",
    ),
    Param(
        name="local_repair_size",
        type="int",
        default=3,
        doc="largest local repair region",
    ),
    Param(
        name="repair_pressure",
        type="float",
        default=10.0,
        doc="priority added to cells missing from the best prefix",
    ),
    Param(name="move_radius", type="int", default=4, doc="largest shift distance"),
    Param(
        name="cluster_size",
        type="int",
        default=3,
        doc="cells moved together by a cluster move",
    ),
    Param(
        name="compaction_moves",
        type="bool",
        default=True,
        doc="include cut and pull moves",
    ),
    Param(
        name="compact_choices",
        type="int",
        default=6,
        doc="ranked candidates a cut or pull samples from",
    ),
    Param(
        name="pull_radius", type="int", default=6, doc="how far a pull may move a cell"
    ),
    Param(
        name="screen_moves",
        type="bool",
        default=False,
        doc="drop a local move whose wire estimate grows before attempting it",
    ),
    Param(
        name="repack_every",
        type="int",
        default=16,
        doc="0, or a repack proposal every N proposals",
    ),
    Param(
        name="repack_size", type="int", default=8, doc="largest repacked neighbourhood"
    ),
    Param(
        name="repack_candidates",
        type="int",
        default=24,
        doc="ranked anchors per repacked cell",
    ),
    Param(name="repack_gap", type="int", default=1, doc="clearance while repacking"),
    Param(
        name="wire_tiebreak",
        type="float",
        default=0.5,
        doc="route-length weight, below one cell of area",
    ),
    Param(
        name="cooling_work",
        type="int",
        default=100000,
        doc="construction cooling horizon in charged units",
    ),
    Param(
        name="layout_cooling_work",
        type="int",
        default=20000,
        doc="improvement cooling horizon in charged units",
    ),
    Param(name="construction_temperature", type="float", default=2.0),
    Param(name="construction_final_temperature", type="float", default=0.05),
    Param(name="layout_temperature", type="float", default=0.02),
    Param(name="layout_final_temperature", type="float", default=0.0000001),
)
POSITIVE = (
    "candidates",
    "move_radius",
    "cluster_size",
    "cooling_work",
    "layout_cooling_work",
    "compact_choices",
    "pull_radius",
    "repack_candidates",
    "local_repair_size",
)


class LocalSolver(BaseSolver):
    """Construct from the current state, then improve; the best is archived independently."""

    id = "local"
    method = "climb"
    resume = "continues"
    params = PARAMS

    def validate(self) -> None:
        for key in POSITIVE:
            if self.opts[key] < 1:
                raise SolverError(f"{key} must be positive")
        if self.opts["frontier_weight"] > 0.5:
            raise SolverError("frontier_weight must not exceed 0.5")
        if self.opts["local_repair_every"] == 1:
            raise SolverError("local_repair_every must be zero or at least two")
        if self.opts["repack_size"] < 2:
            raise SolverError("repack_size must be at least two")
        if self.opts["wire_tiebreak"] >= 1:
            raise SolverError("wire_tiebreak must be less than one cell of area")
        for phase in ("construction", "layout"):
            initial, final = (
                self.opts[f"{phase}_temperature"],
                self.opts[f"{phase}_final_temperature"],
            )
            if not (initial == final == 0 or 0 < final <= initial):
                raise SolverError(
                    f"{phase} temperatures need 0 < final <= initial, or both zero"
                )

    def construct(self, ctx: Any) -> None:
        self.validate()
        self.trajectory = Trajectory(ctx, self.opts, self.method)
        self.trajectory.construct()

    def improve(self, ctx: Any) -> None:
        if ctx.world.unrouted() or len(ctx.world.placements) != len(
            ctx.world.netlist.cells
        ):
            return
        self.trajectory.improve()


@register
class HillClimb(LocalSolver):
    id = "climb"
    method = "climb"


@register
class Anneal(LocalSolver):
    id = "anneal"
    method = "anneal"


__all__ = ["PARAMS", "Anneal", "HillClimb", "LocalSolver"]
