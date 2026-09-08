"""Typed exceptions for KohakuLayout. The bottom of the dependency graph: imports nothing."""


class KohakuLayoutError(Exception):
    """Base class for every framework exception."""


class IRError(KohakuLayoutError):
    """A level is malformed; the message lists every problem found."""


class TextError(IRError):
    """A text-form file does not parse, with the line that failed."""


class PhysicsError(KohakuLayoutError):
    """A physics pack broke its contract or was not found."""


class StateError(KohakuLayoutError):
    """A world operation was used outside its protocol, such as a mutation without a transaction."""


class EngineError(KohakuLayoutError):
    """The engine was driven outside its contract."""


class BudgetExhausted(EngineError):
    """The budget ran out; the attempt in progress is rolled back."""


class SolverError(KohakuLayoutError):
    """A solver or a registry entry is missing or broke its protocol."""


class ServiceError(KohakuLayoutError):
    """A run could not be started, found or resumed."""


class Cancelled(ServiceError):
    """A run was cancelled; the best so far stands, nothing failed."""


class NotAvailable(KohakuLayoutError):
    """A configuration answer: an optional part is not installed or not built. Never a failed solve."""
