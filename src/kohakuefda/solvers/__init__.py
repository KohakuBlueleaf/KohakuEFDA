"""Builtin solver composition; the framework does not import this package."""

from kohakuefda.framework.config import Catalog, Entry
from kohakuefda.solvers.baseline import DEFAULTS, Baseline

SOLVERS = Catalog()
SOLVERS.register(
    Entry("baseline", Baseline, DEFAULTS, "First routed spread, then greedy shrink.")
)
