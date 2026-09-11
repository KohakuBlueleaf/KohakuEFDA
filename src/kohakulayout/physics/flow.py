"""Stage 4 defaults: even splits, proportional capped merges, no memory, no demands, no transfer, no evaluation.

The routed hooks: a commodity per source pin, every pin accepting its capacity, no
production of its own, the acceptance-capped even share, a merge letting each input fill
the outlet, every commodity passing every unit, no links.
"""

from fractions import Fraction
from typing import Any

from kohakulayout.physics.protocol import Made, Mix


class DefaultFlow:
    """What a wire does at a junction and what a cell wants and makes; a pack overrides what its game has."""

    evaluates: bool = False
    evaluator: str = "fixedpoint"

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

    def commodity(self, cell: Any, pin: str) -> str:
        """The name of what a source pin sends; the routed evaluator keeps commodities apart."""
        return f"{cell.id}.{pin}"

    def accept(
        self,
        cell: Any,
        seen: dict[str, frozenset[str]],
        capacities: dict[str, Fraction],
        room: dict[str, Fraction],
    ) -> dict[str, Fraction]:
        """How much each in pin takes of what arrives, given what every in pin has seen and the room on every out pin."""
        return dict(capacities)

    def produce(
        self, cell: Any, inputs: dict[str, Mix], accepts: dict[str, Fraction]
    ) -> Made | None:
        """What a cell's out pins make of the mixes delivered to its in pins; None emits the nets' declared rates."""
        return None

    def share(
        self, rate: Fraction, accepts: tuple[Fraction, ...]
    ) -> tuple[Fraction, ...]:
        """An even share over the outputs that accept, an output accepting less taking that and the rest going round again."""
        out = [Fraction(0)] * len(accepts)
        pool = [i for i, a in enumerate(accepts) if a > 0]
        remaining = Fraction(rate)
        while pool and remaining > 0:
            each = remaining / len(pool)
            capped = [i for i in pool if accepts[i] < each]
            if not capped:
                for i in pool:
                    out[i] += each
                break
            for i in capped:
                out[i] += accepts[i]
                remaining -= accepts[i]
                pool.remove(i)
        return tuple(out)

    def merge_accept(
        self, capacities: tuple[Fraction, ...], outlet: Fraction
    ) -> tuple[Fraction, ...]:
        """How much each input of a merge may bring: each up to the outlet's room."""
        return tuple(min(c, outlet) for c in capacities)

    def passes(self, unit: Any, commodity: str) -> bool:
        return True

    def crosses(self, unit: Any) -> bool:
        """Whether the unit carries each run straight across its cell, one axis apart from the other."""
        return False

    def links(self, netlist: Any) -> tuple[tuple[str, str, str, str], ...]:
        """Pins joined off the grid, as ``(cell, out pin, cell, in pin)``."""
        return ()


__all__ = ["DefaultFlow"]
