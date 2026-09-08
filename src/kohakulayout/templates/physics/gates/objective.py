"""The gates objective: area, wire cells and jumpers, each weighted one."""

from fractions import Fraction
from typing import Any

from kohakulayout.ir import Layout
from kohakulayout.templates.physics.gates.library import JUMPER


class GatesObjective:
    weights: dict[str, Fraction] = {
        "area": Fraction(1),
        "wire_cells": Fraction(1),
        "jumpers": Fraction(1),
        "emitters": Fraction(1),
    }

    def terms(
        self, layout: Layout, metrics: dict[str, Any]
    ) -> dict[str, int | Fraction]:
        return {
            "jumpers": sum(1 for u in layout.units.values() if u.kind == JUMPER.id),
            "emitters": sum(
                1 for u in layout.units.values() if u.owner.startswith("field:")
            ),
        }


__all__ = ["GatesObjective"]
