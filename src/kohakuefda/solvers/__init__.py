"""Builtin solver composition; the framework does not import this package."""

from kohakuefda.framework.config import Catalog, Entry
from kohakuefda.solvers.baseline import DEFAULTS, Baseline
from kohakuefda.solvers.local import DEFAULTS as LOCAL_DEFAULTS
from kohakuefda.solvers.local import (
    TREE_DEFAULTS,
    HillClimbing,
    SimulatedAnnealing,
    TreeHillClimbing,
    TreeSimulatedAnnealing,
)
from kohakuefda.solvers.outline import DEFAULTS as OUTLINE_DEFAULTS
from kohakuefda.solvers.outline import OutlineHillClimbing, OutlineSimulatedAnnealing
from kohakuefda.solvers.regional import DEFAULTS as REGIONAL_DEFAULTS
from kohakuefda.solvers.regional import Regional

SOLVERS = Catalog()
for name, solver in (
    ("hc-outline", OutlineHillClimbing),
    ("sa-outline", OutlineSimulatedAnnealing),
):
    SOLVERS.register(
        Entry(
            name,
            solver,
            OUTLINE_DEFAULTS,
            "Experimental expanded-workspace construction and fixed-outline search.",
        )
    )
for name, solver in (
    ("hc-tree", TreeHillClimbing),
    ("sa-tree", TreeSimulatedAnnealing),
):
    SOLVERS.register(
        Entry(
            name, solver, TREE_DEFAULTS, "Experimental B*-tree-guided coupled search."
        )
    )
SOLVERS.register(
    Entry(
        "hc",
        HillClimbing,
        LOCAL_DEFAULTS,
        "Current-state coupled hill climbing with neutral moves.",
    )
)
SOLVERS.register(
    Entry(
        "sa",
        SimulatedAnnealing,
        LOCAL_DEFAULTS,
        "Coupled simulated annealing with work-based cooling.",
    )
)
SOLVERS.register(
    Entry("baseline", Baseline, DEFAULTS, "First routed spread, then greedy shrink.")
)
SOLVERS.register(
    Entry(
        "regional",
        Regional,
        REGIONAL_DEFAULTS,
        "Coupled frontier and regional reconstruction, then compaction.",
    )
)
