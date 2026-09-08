"""The budget: units and seconds a solver may spend, charged by the engine, never exceeded by more than one charge."""

import time
from collections.abc import Callable
from contextlib import contextmanager
from typing import Any

from kohakulayout.errors import BudgetExhausted


class Budget:
    def __init__(
        self,
        units: int | None = None,
        seconds: float | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.units = units
        self.seconds = seconds
        self.used = 0
        self.charges = 0
        self._clock = clock
        self.started = clock()
        self._caps: list[int] = []

    @property
    def elapsed(self) -> float:
        return self._clock() - self.started

    @property
    def remaining(self) -> int | None:
        caps = [
            *self._caps,
            *([self.used + (self.units - self.used)] if self.units is not None else []),
        ]
        if not caps:
            return None
        return max(0, min(caps) - self.used)

    def exhausted(self) -> bool:
        if self.remaining is not None and self.remaining <= 0:
            return True
        return self.seconds is not None and self.elapsed >= self.seconds

    def charge(self, units: int = 1) -> None:
        """Spend ``units``; raises :class:`BudgetExhausted` once the cap or the clock is passed."""
        self.used += units
        self.charges += 1
        if self.units is not None and self.used > self.units:
            raise BudgetExhausted(
                f"budget of {self.units} units spent; raise units to continue"
            )
        for cap in self._caps:
            if self.used > cap:
                raise BudgetExhausted(
                    f"scoped budget spent at {self.used} units; widen the scope's limit"
                )
        if self.seconds is not None and self.elapsed > self.seconds:
            raise BudgetExhausted(
                f"budget of {self.seconds:g} seconds spent; raise seconds to continue"
            )

    @contextmanager
    def limit(self, units: int) -> Any:
        """A nested cap of ``units`` from now; exhausting it raises inside, the outer budget stays."""
        self._caps.append(self.used + units)
        try:
            yield self
        finally:
            self._caps.pop()

    def snapshot(self) -> dict[str, Any]:
        return {
            "units": self.units,
            "seconds": self.seconds,
            "used": self.used,
            "charges": self.charges,
        }


__all__ = ["Budget"]
