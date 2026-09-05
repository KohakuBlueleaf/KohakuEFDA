"""Regional coupled construction followed by optional complete-state compaction."""

from kohakuefda.framework.config import settings_of
from kohakuefda.framework.control import ConfigurationError
from kohakuefda.solvers.baseline.shrink import Shrink
from kohakuefda.solvers.regional.search import Search

DEFAULTS = {
    "attempts": 128,
    "candidates": 150,
    "gap": 2,
    "gap_cycle": 2,
    "refill_rounds": 1,
    "restart_cycle": 4,
    "repair_threshold": 0.85,
    "radius": 7,
    "radius_cycle": 14,
    "neighbor_cycle": 3,
    "expand_cycle": 5,
    "pressure_decay": 0.7,
    "failure_pressure": 0.5,
    "repair_pressure": 10.0,
    "replace_equal": 0.5,
    "jitter": 3.0,
    "closed_cost": 10000,
    "center_weight": 0.2,
    "corner_weight": 0.015,
    "depot_window": 20,
    "depot_step": 2,
    "shrink_rounds": 200,
}
POSITIVE = (
    "attempts",
    "candidates",
    "gap_cycle",
    "restart_cycle",
    "radius_cycle",
    "neighbor_cycle",
    "expand_cycle",
    "depot_step",
)
PROBABILITIES = ("repair_threshold", "pressure_decay", "replace_equal")


class Regional:
    name = "regional-v1"
    capabilities = frozenset({"place", "relocate", "rebuild"})

    def __init__(self, **settings) -> None:
        self.settings = settings_of(DEFAULTS, settings)
        for key in POSITIVE:
            if self.settings[key] < 1:
                raise ConfigurationError(f"{key} must be positive")
        for key in PROBABILITIES:
            if self.settings[key] > 1:
                raise ConfigurationError(f"{key} must be between zero and one")
        if self.settings["depot_window"] <= self.settings["depot_step"]:
            raise ConfigurationError("depot_window must exceed depot_step")

    def solve(self, context) -> str:
        if context.current is None:
            status = Search(context, self.settings).run()
            if status != "completed":
                return status
        order = tuple(i for i, _ in context.anchors)
        Shrink(context, order, self.settings["shrink_rounds"]).run()
        return "completed"
