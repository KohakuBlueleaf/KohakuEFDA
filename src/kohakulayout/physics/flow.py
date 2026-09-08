"""Stage 4 defaults: even splits, proportional capped merges, no memory, no demands, no transfer, no evaluation."""

from fractions import Fraction
from typing import Any


class DefaultFlow:
    """What a wire does at a junction and what a cell wants and makes; a pack overrides what its game has."""

    evaluates: bool = False

    def split(self, rate: Fraction, live_outputs: int) -> tuple[Fraction, ...]:
        if live_outputs <= 0:
            return ()
        return (Fraction(rate) / live_outputs,) * live_outputs

    def merge(
        self, rates: tuple[Fraction, ...], capacity: Fraction | None
    ) -> tuple[Fraction, ...]:
        total = sum(rates, Fraction(0))
        if capacity is None or total <= capacity or total == 0:
            return tuple(Fraction(r) for r in rates)
        return tuple(Fraction(r) * Fraction(capacity) / total for r in rates)

    def stateful(self) -> bool:
        return False

    def demand(self, cell: Any, pin: str) -> Fraction | None:
        """What a sink pin wants; None means the evaluator checks nothing there."""
        return None

    def transfer(
        self, cell: Any, inputs: dict[str, Fraction]
    ) -> dict[str, Fraction] | None:
        """What a cell's out pins produce from its delivered inputs; None keeps the nets' declared rates."""
        return None


__all__ = ["DefaultFlow"]
