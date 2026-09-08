"""Stage 4 for Endfield: even splitters, summing convergers with stateful priority, planned demands.

A splitter divides evenly over the outputs that accept (JCT-01); a converger sums up to
the carrier's cap and serves its inputs by tier, which the pack records as stateful
rather than models (JCT-02, JCT-03). Each pin demands what the plan routed on it. The
project's evaluator remains the rate oracle over the emitted layout, so the pack does not
evaluate.
"""

from fractions import Fraction
from typing import Any

from kohakuefda.physics.facts import pin_facts
from kohakulayout.physics import DefaultFlow


class EndfieldFlow(DefaultFlow):
    evaluates = False

    def stateful(self) -> bool:
        return True

    def demand(self, cell: Any, pin: str) -> Fraction | None:
        found = pin_facts(cell).get(pin)
        return None if found is None else found[1]


__all__ = ["EndfieldFlow"]
