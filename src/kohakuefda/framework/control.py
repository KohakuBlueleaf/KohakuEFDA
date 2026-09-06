"""Budgets, cancellation and typed execution errors for solver services."""

import time
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager

from kohakuefda.model.control import Cancelled, CancelledError


class FrameworkError(RuntimeError):
    """A solver or extension violated the framework contract."""


class ConfigurationError(ValueError):
    """A setting or extension cannot be used by this run."""


class BudgetExhausted(RuntimeError):
    """A deterministic work limit or elapsed-time limit has been reached."""


class LocalBudgetExhausted(BudgetExhausted):
    """A scoped work allowance ended; the enclosing solve may continue."""


class Rejected(RuntimeError):
    """An ordinary failed edit, carrying a non-proof failure status."""

    def __init__(self, message: str, status: str = "not_found") -> None:
        super().__init__(message)
        self.status = status


class Budget:
    """Shared work accounting with cooperative cancellation and an optional deadline."""

    def __init__(
        self,
        cancelled: Cancelled | None = None,
        max_actions: int = 0,
        seconds: float = 0.0,
    ) -> None:
        self.started = time.monotonic()
        self.cancelled = cancelled
        self.max_actions = max_actions
        self.seconds = seconds
        self.work: Counter[str] = Counter()
        self._limits: list[dict[str, int]] = []

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started

    def check(self) -> None:
        if self.cancelled is not None and self.cancelled():
            raise CancelledError("solver cancelled")
        if self.seconds > 0 and self.elapsed >= self.seconds:
            raise BudgetExhausted("elapsed-time budget exhausted")

    def charge(self, kind: str, count: int = 1) -> None:
        self.check()
        if (
            kind == "actions"
            and self.max_actions > 0
            and self.work[kind] + count > self.max_actions
        ):
            raise BudgetExhausted("action budget exhausted")
        for limits in self._limits:
            if kind in limits and self.work[kind] + count > limits[kind]:
                raise LocalBudgetExhausted(f"local {kind} allowance exhausted")
        self.work[kind] += count

    @contextmanager
    def limit(self, **allowances: int) -> Iterator[None]:
        """Bound named work counters temporarily without resetting global accounting."""
        self.check()
        if any(type(value) is not int or value < 0 for value in allowances.values()):
            raise ConfigurationError(
                "local work allowances must be nonnegative integers"
            )
        limits = {kind: self.work[kind] + value for kind, value in allowances.items()}
        self._limits.append(limits)
        try:
            yield
        finally:
            self._limits.pop()
