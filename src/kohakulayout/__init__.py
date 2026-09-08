"""KohakuLayout: a framework that turns a netlist into a layout on a grid.

The public surface: the levels and their two forms, the one solve function, and the service.
Every name is re-exported from its subpackage and documented there.
"""

from kohakulayout.engine import Budget, Context
from kohakulayout.errors import (
    BudgetExhausted,
    Cancelled,
    EngineError,
    IRError,
    KohakuLayoutError,
    NotAvailable,
    PhysicsError,
    ServiceError,
    SolverError,
    StateError,
    TextError,
)
from kohakulayout.ir import (
    Assessment,
    Frame,
    Layout,
    Netlist,
    Problem,
    Refusal,
    parse_text,
    write,
)
from kohakulayout.ir.json import loads as load
from kohakulayout.pipeline import solve
from kohakulayout.service import LocalService, ProcessService, Request, SolveService

__version__ = "0.0.1"

__all__ = [
    "Assessment",
    "Budget",
    "BudgetExhausted",
    "Cancelled",
    "Context",
    "EngineError",
    "Frame",
    "IRError",
    "KohakuLayoutError",
    "Layout",
    "LocalService",
    "Netlist",
    "NotAvailable",
    "PhysicsError",
    "Problem",
    "ProcessService",
    "Refusal",
    "Request",
    "ServiceError",
    "SolveService",
    "SolverError",
    "StateError",
    "TextError",
    "__version__",
    "load",
    "parse_text",
    "solve",
    "write",
]
