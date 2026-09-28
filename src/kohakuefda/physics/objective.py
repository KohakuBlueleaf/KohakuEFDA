"""The Endfield objective: area and machine count, and what the wiring asks the player to build.

The plan fixes the machines, so ``machines`` is the placed count and moves only while the
layout is incomplete; power is the plan's number (PWR-05) and not a layout term. ``length``
is the wire cells, ``junctions`` the splitters and convergers, ``bridges`` the crossings;
their weights say a junction costs as much area as four cells and a bridge as eight.
"""

from fractions import Fraction
from typing import Any

from kohakuefda.physics.library import BRIDGE, CONVERGER, SPLITTER
from kohakulayout.ir import Layout

JUNCTIONS = frozenset(SPLITTER.values()) | frozenset(CONVERGER.values())
BRIDGES = frozenset(BRIDGE.values())


class EndfieldObjective:
    weights: dict[str, Fraction] = {
        "area": Fraction(1),
        "machines": Fraction(1),
        "length": Fraction(1, 2),
        "junctions": Fraction(4),
        "bridges": Fraction(8),
    }

    def terms(
        self, layout: Layout, metrics: dict[str, Any]
    ) -> dict[str, int | Fraction]:
        units = list(layout.units.values())
        return {
            "machines": int(metrics.get("placed", len(layout.placements))),
            "length": int(metrics.get("wire_cells", 0)),
            "junctions": sum(1 for u in units if u.footprint in JUNCTIONS),
            "bridges": sum(1 for u in units if u.footprint in BRIDGES),
        }


__all__ = ["BRIDGES", "JUNCTIONS", "EndfieldObjective"]
