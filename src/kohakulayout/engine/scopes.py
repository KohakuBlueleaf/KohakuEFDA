"""Scopes: a named phase with an optional budget cap, nested through the context."""

from typing import Any, Self


class Scope:
    def __init__(self, ctx: Any, component: str, units: int | None = None) -> None:
        self.ctx = ctx
        self.component = component
        self.units = units
        self._limit: Any = None
        self._previous = ""

    def __enter__(self) -> Self:
        self._previous = self.ctx.phase
        self.ctx.phase = (
            f"{self._previous}/{self.component}" if self._previous else self.component
        )
        if self.units is not None:
            self._limit = self.ctx.budget.limit(self.units)
            self._limit.__enter__()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        if self._limit is not None:
            self._limit.__exit__(exc_type, exc, tb)
        self.ctx.phase = self._previous
        return False


__all__ = ["Scope"]
