"""The Endfield objective: area and machine count cost, nothing else (the owner's decision).

The plan fixes the machines, so ``machines`` is the placed count and moves only while the
layout is incomplete; power is the plan's number (PWR-05) and not a layout term.
"""

from fractions import Fraction
from typing import Any

from kohakulayout.ir import Layout


class EndfieldObjective:
    weights: dict[str, Fraction] = {"area": Fraction(1), "machines": Fraction(1)}

    def terms(
        self, layout: Layout, metrics: dict[str, Any]
    ) -> dict[str, int | Fraction]:
        return {"machines": int(metrics.get("placed", len(layout.placements)))}


__all__ = ["EndfieldObjective"]
