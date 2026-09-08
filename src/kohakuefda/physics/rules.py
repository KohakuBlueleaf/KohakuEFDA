"""The Endfield deck over a framework layout: what the game refuses, asked once more of the whole.

Each rule repeats a fact the boundaries and carriers enforce cell by cell, so a layout
loaded from a file is judged the same as one the world built.
"""

from collections.abc import Iterable
from typing import Any

from kohakuefda.physics.boundaries import (
    BRICK_KINDS,
    BUS_GROUP,
    PART_KIND,
    ZONE_KIND,
    back_cells,
    inside,
    overlaps,
    rect_of,
    seated,
    touching,
    zone_rect,
)
from kohakuefda.physics.fabric import area_rect
from kohakuefda.physics.library import (
    BELT,
    PIPE,
    PIPE_UNIT_LIMIT,
    RUN_LIMIT,
    UNIT_CARRIER,
)
from kohakulayout.ir import Finding, Layout
from kohakulayout.physics import FunctionRule


def _finding(rule: str, subject: str, message: str) -> Finding:
    return Finding(rule=rule, severity="error", subject=subject, message=message)


def area(world: Any, layout: Layout, metrics: dict[str, Any]) -> Iterable[Finding]:
    box = area_rect(world.fabric)
    for cell_id, placement in layout.placements.items():
        if not inside(rect_of(world, cell_id, placement), box):
            yield _finding(
                "endfield.area",
                f"cell:{cell_id}",
                f"{cell_id} leaves the Core AIC Area",
            )


def belt_ring(world: Any, layout: Layout, metrics: dict[str, Any]) -> Iterable[Finding]:
    x0, y0, x1, y1 = area_rect(world.fabric)
    for net_id, wire in layout.wires.items():
        for segment in wire.segments:
            if segment.carrier != BELT:
                continue
            if any(not (x0 <= x < x1 and y0 <= y < y1) for x, y in segment.cells):
                yield _finding(
                    "endfield.belt_ring",
                    f"net:{net_id}",
                    f"belt {net_id} leaves the area",
                )
                break


def run_length(
    world: Any, layout: Layout, metrics: dict[str, Any]
) -> Iterable[Finding]:
    for net_id, wire in layout.wires.items():
        for segment in wire.segments:
            limit = RUN_LIMIT.get(segment.carrier)
            if limit is not None and len(segment.cells) > limit:
                yield _finding(
                    "endfield.run_length",
                    f"net:{net_id}",
                    f"{segment.carrier} run of {len(segment.cells)} cells exceeds {limit}",
                )


def pipe_units(
    world: Any, layout: Layout, metrics: dict[str, Any]
) -> Iterable[Finding]:
    count = sum(
        1 for u in layout.units.values() if UNIT_CARRIER.get(u.footprint) == PIPE
    )
    if count > PIPE_UNIT_LIMIT:
        yield _finding(
            "endfield.pipe_units",
            "layout",
            f"{count} pipe units exceed the limit of {PIPE_UNIT_LIMIT}",
        )


def bus(world: Any, layout: Layout, metrics: dict[str, Any]) -> Iterable[Finding]:
    group = world.netlist.groups.get(BUS_GROUP)
    if group is None:
        return
    placed = [
        (world.netlist.cells[m], layout.placements[m])
        for m in group.members
        if m in layout.placements
    ]
    parts = [(c, p) for c, p in placed if c.kind == PART_KIND]
    if not parts:
        return
    rects = {c.id: rect_of(world, c.id, p) for c, p in parts}
    reached = {parts[0][0].id}
    frontier = [parts[0][0].id]
    while frontier:
        current = frontier.pop()
        for other, rect in rects.items():
            if other not in reached and touching(rects[current], rect):
                reached.add(other)
                frontier.append(other)
    for part_id in rects:
        if part_id not in reached:
            yield _finding(
                "endfield.bus",
                f"cell:{part_id}",
                f"{part_id} is not in the bus cluster",
            )
    cells = {
        (x, y)
        for x0, y0, x1, y1 in rects.values()
        for y in range(y0, y1)
        for x in range(x0, x1)
    }
    for cell, placement in placed:
        if (
            cell.kind in BRICK_KINDS
            and cell.constraint.kind != "slot"
            and back_cells(world, cell, placement)
            and not seated(world, cell, placement, cells)
        ):
            yield _finding(
                "endfield.bus", f"cell:{cell.id}", f"{cell.id} does not seat on the bus"
            )


def zones(world: Any, layout: Layout, metrics: dict[str, Any]) -> Iterable[Finding]:
    boxes: list[tuple[str, tuple[int, int, int, int]]] = []
    for group_id, group in world.netlist.groups.items():
        if not group_id.startswith(ZONE_KIND):
            continue
        members = [
            (world.netlist.cells[m], layout.placements[m])
            for m in group.members
            if m in layout.placements
        ]
        units = [(c, p) for c, p in members if c.kind == ZONE_KIND]
        if not units:
            continue
        zone = zone_rect(world, units[0][0].id, units[0][1])
        boxes.append((units[0][0].id, zone))
        for cell, placement in members:
            if cell.kind != ZONE_KIND and not inside(
                rect_of(world, cell.id, placement), zone
            ):
                yield _finding(
                    "endfield.zone", f"cell:{cell.id}", f"{cell.id} leaves its gas zone"
                )
    for index, (first, box) in enumerate(boxes):
        for other, other_box in boxes[index + 1 :]:
            if overlaps(box, other_box):
                yield _finding(
                    "endfield.zone",
                    f"cell:{first}",
                    f"zones of {first} and {other} overlap",
                )


RULES = (
    FunctionRule("endfield.area", "error", area),
    FunctionRule("endfield.belt_ring", "error", belt_ring),
    FunctionRule("endfield.run_length", "error", run_length),
    FunctionRule("endfield.pipe_units", "error", pipe_units),
    FunctionRule("endfield.bus", "error", bus),
    FunctionRule("endfield.zone", "error", zones),
)

__all__ = ["RULES", "area", "belt_ring", "bus", "pipe_units", "run_length", "zones"]
