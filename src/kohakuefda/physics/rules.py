"""The Endfield deck over a framework layout: what the game refuses, asked once more of the whole.

Each rule repeats a fact the boundaries and carriers enforce cell by cell, so a layout
loaded from a file is judged the same as one the world built: the area and the ring
(REG-02, REG-03, LOG-08), run length (LOG-05), the pipe-unit count, the bus and the
bricks on it (DEP-06, DEP-08, DEP-09, DEP-18), gas zones (ENV-01, ENV-02), one
Automation-Core (PLC-05, DEP-03), conduit links (DEP-16), and wiring that branches and
merges only through junction units and ends only at pins (LOG-07).
"""

from collections.abc import Iterable
from typing import Any

from kohakuefda.physics.boundaries import (
    BRICK_KINDS,
    BUS_GROUP,
    BUS_PORT,
    PART_KIND,
    ZONE_KIND,
    back_cells,
    facts,
    inside,
    overlaps,
    rect_of,
    seated,
    touching,
    zone_rect,
)
from kohakuefda.physics.fabric import FIXED, area_rect
from kohakuefda.physics.library import (
    BELT,
    CONDUIT_LINK_MAX,
    PIPE,
    PIPE_UNIT_LIMIT,
    RUN_LIMIT,
    UNIT_CARRIER,
)
from kohakulayout.ir import Finding, Layout
from kohakulayout.physics import FunctionRule

CORE_KIND = "core"
INLET_KIND = "inlet"
OUTLET_KIND = "outlet"


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
    """A continuous run ends at a unit of its own net (LOG-05): each stretch between them stays within the carrier's limit."""
    for net_id, wire in layout.wires.items():
        cuts = {
            (layout.units[u].x, layout.units[u].y)
            for u in wire.units
            if u in layout.units
        }
        for segment in wire.segments:
            limit = RUN_LIMIT.get(segment.carrier)
            if limit is None:
                continue
            longest = run = 0
            for cell in segment.cells:
                run = 0 if cell in cuts else run + 1
                longest = max(longest, run)
            if longest > limit:
                yield _finding(
                    "endfield.run_length",
                    f"net:{net_id}",
                    f"{segment.carrier} run of {longest} cells exceeds {limit}",
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


def placed_of_kind(world: Any, layout: Layout, kinds: frozenset[str]) -> list:
    return [
        (world.netlist.cells[cell_id], placement)
        for cell_id, placement in layout.placements.items()
        if cell_id in world.netlist.cells and world.netlist.cells[cell_id].kind in kinds
    ]


def bus(world: Any, layout: Layout, metrics: dict[str, Any]) -> Iterable[Finding]:
    """Every bus part in a touching cluster around a port (DEP-08, DEP-09); every brick off a slot seated on a part or the fixed bus (DEP-06, DEP-18)."""
    parts = placed_of_kind(world, layout, frozenset({PART_KIND}))
    bricks = [
        (c, p)
        for c, p in placed_of_kind(world, layout, BRICK_KINDS)
        if c.group == BUS_GROUP
    ]
    rects = {c.id: rect_of(world, c.id, p) for c, p in parts}
    if parts:
        reached = {c.id for c, _ in parts if c.footprint == BUS_PORT}
        frontier = list(reached)
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
    fixed = world.fabric.regions.get(FIXED)
    if fixed is not None:
        cells |= set(fixed.cells())
    for cell, placement in bricks:
        if cell.constraint.kind == "slot" or not back_cells(world, cell, placement):
            continue
        if not cells:
            yield _finding(
                "endfield.bus",
                f"cell:{cell.id}",
                f"{cell.id} has no Depot Bus to seat on",
            )
        elif not seated(world, cell, placement, cells):
            yield _finding(
                "endfield.bus", f"cell:{cell.id}", f"{cell.id} does not seat on the bus"
            )


def zones(world: Any, layout: Layout, metrics: dict[str, Any]) -> Iterable[Finding]:
    """A grouped member inside its unit's zone, every environment machine inside some zone, zones apart (ENV-01, ENV-02)."""
    boxes = [
        (c.id, zone_rect(world, c.id, p))
        for c, p in placed_of_kind(world, layout, frozenset({ZONE_KIND}))
    ]
    by_unit = dict(boxes)
    for group_id, group in world.netlist.groups.items():
        if not group_id.startswith(ZONE_KIND):
            continue
        units = [m for m in group.members if m in by_unit]
        if not units:
            continue
        zone = by_unit[units[0]]
        for member in group.members:
            placement = layout.placements.get(member)
            cell = world.netlist.cells.get(member)
            if placement is None or cell is None or cell.kind == ZONE_KIND:
                continue
            if not inside(rect_of(world, member, placement), zone):
                yield _finding(
                    "endfield.zone", f"cell:{member}", f"{member} leaves its gas zone"
                )
    for cell_id, placement in layout.placements.items():
        cell = world.netlist.cells.get(cell_id)
        if cell is None or cell.kind == ZONE_KIND or not facts(cell).get("env"):
            continue
        rect = rect_of(world, cell_id, placement)
        if not any(inside(rect, box) for _, box in boxes):
            yield _finding(
                "endfield.zone",
                f"cell:{cell_id}",
                f"{cell_id} runs a {facts(cell)['env']} recipe outside every gas zone",
            )
    for index, (first, box) in enumerate(boxes):
        for other, other_box in boxes[index + 1 :]:
            if overlaps(box, other_box):
                yield _finding(
                    "endfield.zone",
                    f"cell:{first}",
                    f"zones of {first} and {other} overlap",
                )


def core(world: Any, layout: Layout, metrics: dict[str, Any]) -> Iterable[Finding]:
    """At most one Automation-Core stands in a layout (PLC-05, DEP-03)."""
    cores = placed_of_kind(world, layout, frozenset({CORE_KIND}))
    if len(cores) > 1:
        yield _finding(
            "endfield.core",
            "layout",
            f"{len(cores)} Automation-Cores; a Core AIC Area has one",
        )


def conduit(world: Any, layout: Layout, metrics: dict[str, Any]) -> Iterable[Finding]:
    """Every conduit link joins a placed inlet to a placed outlet within ``CONDUIT_LINK_MAX`` cells (DEP-16)."""
    for link in facts(world.netlist).get("links", ()):
        inlet_id, outlet_id = str(link).split(":")
        ends = [
            (layout.placements.get(end), world.netlist.cells.get(end))
            for end in (inlet_id, outlet_id)
        ]
        if any(p is None or c is None for p, c in ends):
            yield _finding(
                "endfield.conduit",
                f"cell:{inlet_id}",
                f"conduit link {inlet_id}:{outlet_id} names an unplaced end",
            )
            continue
        (inlet, in_cell), (outlet, out_cell) = ends
        if in_cell.kind != INLET_KIND or out_cell.kind != OUTLET_KIND:
            yield _finding(
                "endfield.conduit",
                f"cell:{inlet_id}",
                f"conduit link {inlet_id}:{outlet_id} must join an inlet to an outlet",
            )
        distance = abs(inlet.x - outlet.x) + abs(inlet.y - outlet.y)
        if distance > CONDUIT_LINK_MAX:
            yield _finding(
                "endfield.conduit",
                f"cell:{inlet_id}",
                f"conduit ends are {distance} cells apart; the limit is {CONDUIT_LINK_MAX}",
            )


def wiring(world: Any, layout: Layout, metrics: dict[str, Any]) -> Iterable[Finding]:
    """Along its segments a wire branches or merges only on a junction unit, ends only on a pin's attach cell or a unit, and visits a cell once (LOG-07)."""
    netlist = world.netlist
    for net_id, wire in layout.wires.items():
        net = netlist.nets.get(net_id)
        if net is None:
            continue
        links: dict[tuple[int, int], set[tuple[int, int]]] = {}
        visits: dict[tuple[int, int], int] = {}
        for segment in wire.segments:
            cells = list(segment.cells)
            for index, xy in enumerate(cells):
                visits[xy] = visits.get(xy, 0) + 1
                links.setdefault(xy, set())
                if index:
                    links[xy].add(cells[index - 1])
                    links[cells[index - 1]].add(xy)
        units = {
            (layout.units[u].x, layout.units[u].y)
            for u in wire.units
            if u in layout.units
        }
        attach: set[tuple[int, int]] = set()
        for ref in net.pins():
            found = layout.attach(netlist, ref, wire.port_of(ref))
            if found is not None:
                attach.add(found)
        for xy, count in visits.items():
            if count > 1 and xy not in units and xy not in attach:
                yield _finding(
                    "endfield.wiring", f"net:{net_id}", f"{net_id} visits {xy} twice"
                )
        for xy, near in links.items():
            if xy in units:
                continue
            if len(near) > 2:
                yield _finding(
                    "endfield.wiring",
                    f"net:{net_id}",
                    f"{net_id} branches at {xy} with no junction unit",
                )
            elif xy in attach and len(near) > 1:
                yield _finding(
                    "endfield.wiring",
                    f"net:{net_id}",
                    f"{net_id} merges or splits at the port cell {xy}",
                )
            elif xy not in attach and len(near) < 2:
                yield _finding(
                    "endfield.wiring",
                    f"net:{net_id}",
                    f"{net_id} ends at {xy} on no port",
                )


RULES = (
    FunctionRule("endfield.area", "error", area),
    FunctionRule("endfield.belt_ring", "error", belt_ring),
    FunctionRule("endfield.run_length", "error", run_length),
    FunctionRule("endfield.pipe_units", "error", pipe_units),
    FunctionRule("endfield.bus", "error", bus),
    FunctionRule("endfield.zone", "error", zones),
    FunctionRule("endfield.core", "error", core),
    FunctionRule("endfield.conduit", "error", conduit),
    FunctionRule("endfield.wiring", "error", wiring),
)

__all__ = [
    "CORE_KIND",
    "INLET_KIND",
    "OUTLET_KIND",
    "RULES",
    "area",
    "belt_ring",
    "bus",
    "conduit",
    "core",
    "pipe_units",
    "placed_of_kind",
    "run_length",
    "wiring",
    "zones",
]
