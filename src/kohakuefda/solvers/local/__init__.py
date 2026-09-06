"""Matched hill-climbing and simulated-annealing heuristic baselines."""

from kohakuefda.framework.config import settings_of
from kohakuefda.framework.control import ConfigurationError
from kohakuefda.solvers.local.search import Trajectory

DEFAULTS = {
    "construction_steps": 128,
    "improvement_steps": 2000,
    "candidates": 150,
    "gap": 2,
    "frontier_weight": 0.0,
    "insertion_lookahead": 6,
    "local_repair_every": 0,
    "local_repair_size": 3,
    "repair_actions": 12000,
    "repair_route_calls": 24000,
    "move_radius": 4,
    "cluster_size": 3,
    "compaction_moves": True,
    "repack_every": 16,
    "repack_size": 8,
    "repack_candidates": 24,
    "repack_gap": 1,
    "until_budget": True,
    "compact_choices": 6,
    "pull_radius": 6,
    "wire_tiebreak": 0.5,
    "cooling_work": 100000,
    "layout_cooling_work": 20000,
    "construction_temperature": 2.0,
    "construction_final_temperature": 0.05,
    "layout_temperature": 0.02,
    "layout_final_temperature": 0.0000001,
}
POSITIVE = (
    "candidates",
    "repair_actions",
    "repair_route_calls",
    "move_radius",
    "cluster_size",
    "cooling_work",
    "layout_cooling_work",
    "compact_choices",
    "pull_radius",
    "repack_candidates",
    "local_repair_size",
)


class LocalSolver:
    """Construct and improve from current state; archive the best independently."""

    capabilities = frozenset({"place", "relocate", "reroute"})

    def __init__(self, **settings) -> None:
        self.settings = settings_of(DEFAULTS, settings)
        for key in POSITIVE:
            if self.settings[key] < 1:
                raise ConfigurationError(f"{key} must be positive")
        if self.settings["frontier_weight"] > 0.5:
            raise ConfigurationError("frontier_weight must not exceed 0.5")
        if self.settings["local_repair_every"] == 1:
            raise ConfigurationError("local_repair_every must be zero or at least two")
        if self.settings["repack_size"] < 2:
            raise ConfigurationError("repack_size must be at least two")
        if self.settings["wire_tiebreak"] >= 1:
            raise ConfigurationError("wire_tiebreak must be less than one area cell")
        for phase in ("construction", "layout"):
            initial = self.settings[f"{phase}_temperature"]
            final = self.settings[f"{phase}_final_temperature"]
            if not (initial == final == 0 or 0 < final <= initial):
                raise ConfigurationError(
                    f"{phase} temperatures require 0 < final <= initial, or both zero"
                )

    def solve(self, context) -> str:
        trajectory = Trajectory(context, self.settings, self.method)
        if context.current is None and not trajectory.construct():
            return "no_solution_found"
        trajectory.improve()
        return "completed"


class HillClimbing(LocalSolver):
    name = "hill-climbing-v1"
    method = "hc"


class SimulatedAnnealing(LocalSolver):
    name = "simulated-annealing-v1"
    method = "sa"
