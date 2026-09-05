"""Public framework API; imports no concrete solver."""

from kohakuefda.framework.actions import ActionHandler, Workspace
from kohakuefda.framework.config import Catalog, Entry
from kohakuefda.framework.context import Context
from kohakuefda.framework.control import (
    Budget,
    BudgetExhausted,
    ConfigurationError,
    FrameworkError,
    Rejected,
)
from kohakuefda.framework.problem import problem_of
from kohakuefda.framework.runtime import Solver, solve
from kohakuefda.model.solver import (
    Action,
    Candidate,
    Problem,
    Scope,
    Snapshot,
    SolveEvent,
    SolveResult,
)

__all__ = [
    "Action",
    "ActionHandler",
    "Budget",
    "BudgetExhausted",
    "Candidate",
    "Catalog",
    "ConfigurationError",
    "Context",
    "Entry",
    "FrameworkError",
    "Problem",
    "Rejected",
    "Scope",
    "Snapshot",
    "SolveEvent",
    "SolveResult",
    "Solver",
    "Workspace",
    "problem_of",
    "solve",
]
