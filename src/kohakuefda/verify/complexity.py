"""Build complexity of a layout: how much wire, how many junctions and bridges, how many kinds
of thing, how straight the wiring runs, and, once units exist, how repetitive the layout is.
"""

from fractions import Fraction
from itertools import pairwise

from kohakuefda.model.base import EfdaModel
from kohakuefda.model.layout import Layout, Segment
from kohakuefda.model.units import Hierarchy
from kohakuefda.physics.library import BELT, BRIDGE, CONVERGER, PIPE, SPLITTER

STRAIGHT_RUN = 8


class Complexity(EfdaModel):
    """What a layout asks the player to build beyond its machines."""

    belt_cells: int = 0
    pipe_cells: int = 0
    bends: int = 0
    splitters: int = 0
    convergers: int = 0
    belt_bridges: int = 0
    pipe_junctions: int = 0
    pipe_bridges: int = 0
    kinds: int = 0
    straight: Fraction = Fraction(0)
    unit_types: int = 0
    unit_copies: int = 0
    global_nets: int = 0

    @property
    def junctions(self) -> int:
        return self.splitters + self.convergers + self.pipe_junctions

    @property
    def bridges(self) -> int:
        return self.belt_bridges + self.pipe_bridges


def runs(segment: Segment) -> list[int]:
    """The lengths of the segment's maximal straight runs, in order."""
    cells = segment.cells
    if len(cells) < 2:
        return [len(cells)]
    out: list[int] = []
    length = 1
    heading = None
    for (ax, ay), (bx, by) in pairwise(cells):
        step = (bx - ax, by - ay)
        if heading is None or step == heading:
            length += 1
        else:
            out.append(length)
            length = 2
        heading = step
    out.append(length)
    return out


def complexity(layout: Layout) -> Complexity:
    """The layout's build complexity from its segments, units and machines."""
    out = Complexity()
    straight = 0
    total = 0
    for segment in layout.segments:
        cells = len(segment.cells)
        total += cells
        if segment.kind == "belt":
            out.belt_cells += cells
        else:
            out.pipe_cells += cells
        lengths = runs(segment)
        out.bends += max(0, len(lengths) - 1)
        straight += sum(n for n in lengths if n >= STRAIGHT_RUN)
    for unit in layout.units:
        if unit.unit_id == SPLITTER[BELT]:
            out.splitters += 1
        elif unit.unit_id == CONVERGER[BELT]:
            out.convergers += 1
        elif unit.unit_id == BRIDGE[BELT]:
            out.belt_bridges += 1
        elif unit.unit_id in (SPLITTER[PIPE], CONVERGER[PIPE]):
            out.pipe_junctions += 1
        elif unit.unit_id == BRIDGE[PIPE]:
            out.pipe_bridges += 1
    out.kinds = len(
        {m.machine_id for m in layout.machines} | {u.unit_id for u in layout.units}
    )
    out.straight = Fraction(straight, total) if total else Fraction(0)
    return out


def with_units(found: Complexity, hierarchy: Hierarchy) -> Complexity:
    """The same report with the plan's top-level tile types, their copies and the flows between them."""
    return found.model_copy(
        update={
            "unit_types": len(hierarchy.top),
            "unit_copies": sum(t.copies for t in hierarchy.top),
            "global_nets": sum(1 for f in hierarchy.flows if f.source and f.sink),
        }
    )


def complexity_text(found: Complexity) -> str:
    """One line for logs and benchmark summaries."""
    return (
        f"belts={found.belt_cells} pipes={found.pipe_cells} bends={found.bends} "
        f"junctions={found.junctions} bridges={found.bridges} kinds={found.kinds} "
        f"straight={float(found.straight):.2f} units={found.unit_types}x{found.unit_copies} "
        f"global={found.global_nets}"
    )


__all__ = [
    "STRAIGHT_RUN",
    "Complexity",
    "complexity",
    "complexity_text",
    "runs",
    "with_units",
]
