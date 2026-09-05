"""The builtin first-feasible spread and greedy-shrink solver."""

from kohakuefda.framework.config import settings_of
from kohakuefda.framework.control import ConfigurationError
from kohakuefda.solvers.baseline.parallel import build_parallel
from kohakuefda.solvers.baseline.shrink import Shrink
from kohakuefda.solvers.baseline.spread import Spread

DEFAULTS = {
    "spread_attempts": 32000,
    "spread_slice": 64,
    "spread_gap": 0,
    "spread_widest": 6,
    "shrink_rounds": 200,
    "flow_order": "bottom-up",
}


class Baseline:
    name = "spread-greedy-v1"
    capabilities = frozenset({"place", "relocate", "rebuild"})

    def __init__(self, **settings) -> None:
        self.settings = settings_of(DEFAULTS, settings)
        if self.settings["spread_widest"] < self.settings["spread_gap"]:
            raise ConfigurationError("spread_widest cannot be below spread_gap")
        if self.settings["spread_attempts"] < 1 or self.settings["spread_slice"] < 1:
            raise ConfigurationError("spread budgets must be positive")
        if self.settings["flow_order"] not in ("top-down", "bottom-up"):
            raise ConfigurationError("invalid flow_order")
        self.spread = None

    def solve(self, context) -> str:
        if (
            context.current is None
            and context.workers > 1
            and context.forkable
            and not context.budget.max_actions
        ):
            order = build_parallel(context, self.settings)
            if order is None:
                return "no_solution_found"
        elif context.current is None:
            self.spread = Spread(context, self.settings)
            if not self.spread.run():
                return "no_solution_found"
            order = tuple(self.spread.order)
        else:
            order = tuple(i for i, _ in context.view.anchors)
        Shrink(context, order, self.settings["shrink_rounds"]).run()
        return "completed"
