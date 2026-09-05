"""Builtin solver composition; the framework does not import this package."""

from kohakuefda.framework.config import Catalog, Entry
from kohakuefda.solvers.baseline import DEFAULTS, Baseline
from kohakuefda.solvers.regional import DEFAULTS as REGIONAL_DEFAULTS
from kohakuefda.solvers.regional import Regional

SOLVERS = Catalog()
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
