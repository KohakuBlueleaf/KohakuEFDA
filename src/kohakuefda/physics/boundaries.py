"""Stage 3 for Endfield: where a cell may stand, by its constraint and its group.

Machines stay inside the Core AIC Area and only pipes cross into the ring (REG-02, REG-03,
LOG-08). An outside input stands on the border with its pipe leaving inward (RES-09). A
Valley IV brick stands on one of the fixed bus's slots (DEP-06, DEP-12, DEP-18); a Wuling
brick's back face touches a bus part and the parts form one touching cluster (DEP-06,
DEP-09, DEP-17). A gas zone holds the whole footprint of every machine it serves and
zones do not overlap (ENV-01, ENV-02).
"""

from collections.abc import Iterable
from typing import Any

from kohakuefda.physics.fabric import (
    FIXED,
    NAMESPACE,
    RING,
    Rect,
    area_rect,
    entry_rect,
    slots_of,
)
from kohakuefda.physics.library import PIPE
from kohakulayout.ir import Cell, Placement, Refusal
from kohakulayout.ir.geometry import SIDES, attach_cell, rotate_side, rotate_size
from kohakulayout.physics import Anchor, DefaultBoundaries

BUS_GROUP = "bus"
BUS_PORT = "log_hongs_bus_source"
BRICK_KINDS = frozenset({"unloader", "loader"})
PART_KIND = "depot"
ZONE_KIND = "zone"
ZONE_REACH = 5
BRICK_SEAT = 2
BRICK_SEAT_MIDDLE: bool = True
BUS_ROOM = 2
SEAT = "seat"
CLUSTER = "cluster"
OPPOSITE = {"N": "S", "S": "N", "E": "W", "W": "E"}


def facts(cell: Cell) -> dict[str, Any]:
    return cell.attrs.get(NAMESPACE, {})


def turn(side_from: str, side_to: str) -> int:
    """The rotation that carries ``side_from`` onto ``side_to``."""
    return 90 * ((SIDES.index(side_to) - SIDES.index(side_from)) % 4)


def rect_of(world: Any, cell_id: str, placement: Placement) -> Rect:
    fp = world.footprint_of(cell_id)
    w, h = rotate_size(fp.width, fp.height, placement.rot)
    return (placement.x, placement.y, placement.x + w, placement.y + h)


def inside(inner: Rect, outer: Rect) -> bool:
    return (
        outer[0] <= inner[0]
        and outer[1] <= inner[1]
        and inner[2] <= outer[2]
        and inner[3] <= outer[3]
    )


def overlaps(a: Rect, b: Rect) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def touching(a: Rect, b: Rect) -> bool:
    """Whether two rectangles share an edge of positive length."""
    side_by_side = (a[2] == b[0] or b[2] == a[0]) and a[1] < b[3] and b[1] < a[3]
    stacked = (a[3] == b[1] or b[3] == a[1]) and a[0] < b[2] and b[0] < a[2]
    return side_by_side or stacked


def anchors_in(world: Any, cell: Cell, rect: Rect) -> Iterable[Anchor]:
    """Every rotation and position keeping the footprint inside ``rect``."""
    fp = world.footprint_of(cell.id)
    if fp is None:
        return
    x0, y0, x1, y1 = rect
    for rot in fp.rotations:
        rw, rh = rotate_size(fp.width, fp.height, rot)
        for y in range(y0, y1 - rh + 1):
            for x in range(x0, x1 - rw + 1):
                yield Anchor(x=x, y=y, rot=rot)


def port_side(world: Any, cell: Cell) -> str | None:
    """The side of the cell's first pin's port at rotation zero."""
    fp = world.footprint_of(cell.id)
    pins = world.netlist.pins_of(cell.id)
    if fp is None or not pins or not pins[0].ports:
        return None
    port = fp.port(pins[0].ports[0])
    return port.side if port is not None else None


def back_side(world: Any, cell: Cell, rot: int) -> str | None:
    side = port_side(world, cell)
    return None if side is None else rotate_side(OPPOSITE[side], rot)


def back_cells(
    world: Any, cell: Cell, placement: Placement
) -> tuple[tuple[int, int], ...]:
    """The cells a brick's back face looks at."""
    side = back_side(world, cell, placement.rot)
    if side is None:
        return ()
    x0, y0, x1, y1 = rect_of(world, cell.id, placement)
    if side in ("N", "S"):
        y = y0 - 1 if side == "N" else y1
        return tuple((x, y) for x in range(x0, x1))
    x = x0 - 1 if side == "W" else x1
    return tuple((x, y) for y in range(y0, y1))


def zone_rect(world: Any, cell_id: str, placement: Placement) -> Rect:
    x0, y0, x1, y1 = rect_of(world, cell_id, placement)
    return (x0 - ZONE_REACH, y0 - ZONE_REACH, x1 + ZONE_REACH, y1 + ZONE_REACH)


def placed_members(
    world: Any, group: str, exclude: str
) -> list[tuple[Cell, Placement]]:
    grp = world.netlist.groups.get(group)
    if grp is None:
        return []
    out = []
    for member in grp.members:
        placement = world.placements.get(member)
        if placement is not None and member != exclude:
            out.append((world.netlist.cells[member], placement))
    return out


def edge_anchors(world: Any, cell: Cell) -> Iterable[Anchor]:
    """Border cells of the entry area on the fabric's entry sides, the pin's port facing inward."""
    fp = world.footprint_of(cell.id)
    side0 = port_side(world, cell)
    if fp is None or side0 is None:
        return
    x0, y0, x1, y1 = entry_rect(world.fabric)
    for border in world.fabric.entries:
        rot = turn(side0, OPPOSITE[border])
        if rot not in fp.rotations:
            continue
        rw, rh = rotate_size(fp.width, fp.height, rot)
        if border in ("W", "E"):
            x = x0 if border == "W" else x1 - rw
            for y in range(y0, y1 - rh + 1):
                yield Anchor(x=x, y=y, rot=rot)
        else:
            y = y0 if border == "N" else y1 - rh
            for x in range(x0, x1 - rw + 1):
                yield Anchor(x=x, y=y, rot=rot)


def slot_anchors(world: Any, cell: Cell) -> Iterable[Anchor]:
    """The fixed bus's slots, each with the rotation turning the brick's back onto the bus."""
    fp = world.footprint_of(cell.id)
    side0 = port_side(world, cell)
    if fp is None or side0 is None:
        return
    for x, y, side in slots_of(world.fabric):
        rot = turn(OPPOSITE[side0], side)
        if rot in fp.rotations:
            yield Anchor(x=x, y=y, rot=rot)


def bus_anchors(world: Any, cell: Cell, area: Rect) -> Iterable[Anchor]:
    """A part behind a brick no part seats yet, else against the cluster, kept two cells off the border for its bricks and their belts; a brick with its back on a part."""
    mates = placed_members(world, BUS_GROUP, cell.id)
    parts = [(c, p) for c, p in mates if c.kind == PART_KIND]
    bricks = [(c, p) for c, p in mates if c.kind in BRICK_KINDS]
    if cell.kind in BRICK_KINDS and not parts:
        return
    if cell.kind == PART_KIND:
        x0, y0, x1, y1 = area
        area = (x0 + BUS_ROOM, y0 + BUS_ROOM, x1 - BUS_ROOM, y1 - BUS_ROOM)
    if not parts and not bricks:
        yield from anchors_in(world, cell, area)
        return
    part_rects = [rect_of(world, c.id, p) for c, p in parts]
    part_cells = {
        (x, y)
        for x0, y0, x1, y1 in part_rects
        for y in range(y0, y1)
        for x in range(x0, x1)
    }
    backs = {c for cell_b, p in bricks for c in back_cells(world, cell_b, p)}
    fp = world.footprint_of(cell.id)
    unseated = {
        c
        for cell_b, p in bricks
        if not seated(world, cell_b, p, part_cells)
        for c in back_cells(world, cell_b, p)
    }
    serving: list[Anchor] = []
    joining: list[Anchor] = []
    for anchor in anchors_in(world, cell, area):
        w, h = rotate_size(fp.width, fp.height, anchor.rot)
        rect = (anchor.x, anchor.y, anchor.x + w, anchor.y + h)
        if cell.kind == PART_KIND:
            covers = {
                (x, y)
                for x, y in backs
                if rect[0] <= x < rect[2] and rect[1] <= y < rect[3]
            }
            if covers & unseated:
                serving.append(anchor)
            elif any(touching(rect, r) for r in part_rects) or covers:
                joining.append(anchor)
        elif part_cells:
            placement = Placement(cell=cell.id, x=anchor.x, y=anchor.y, rot=anchor.rot)
            own = {
                (x, y) for y in range(rect[1], rect[3]) for x in range(rect[0], rect[2])
            }
            if not (own & part_cells) and seated(world, cell, placement, part_cells):
                yield anchor
        else:
            yield anchor
    if cell.kind == PART_KIND:
        yield from serving or joining


def seated(
    world: Any, cell: Cell, placement: Placement, part_cells: set[tuple[int, int]]
) -> bool:
    """A brick seats when at least ``BRICK_SEAT`` back cells touch bus cells, the middle among them when ``BRICK_SEAT_MIDDLE`` (DEP-18)."""
    backs = back_cells(world, cell, placement)
    if not backs:
        return False
    hits = [c in part_cells for c in backs]
    return sum(hits) >= BRICK_SEAT and (hits[len(hits) // 2] or not BRICK_SEAT_MIDDLE)


def zone_anchors(world: Any, cell: Cell, area: Rect) -> Iterable[Anchor]:
    """A member inside its unit's zone; a unit whose zone holds every placed member."""
    mates = placed_members(world, cell.group or "", cell.id)
    units = [(c, p) for c, p in mates if c.kind == ZONE_KIND]
    members = [(c, p) for c, p in mates if c.kind != ZONE_KIND]
    if cell.kind == ZONE_KIND:
        if not members:
            yield from anchors_in(world, cell, area)
            return
        rects = [rect_of(world, c.id, p) for c, p in members]
        for anchor in anchors_in(world, cell, area):
            placement = Placement(cell=cell.id, x=anchor.x, y=anchor.y, rot=anchor.rot)
            zone = zone_rect(world, cell.id, placement)
            if all(inside(r, zone) for r in rects):
                yield anchor
        return
    if not units:
        yield from anchors_in(world, cell, area)
        return
    zone = zone_rect(world, units[0][0].id, units[0][1])
    x0, y0, x1, y1 = area
    window = (max(x0, zone[0]), max(y0, zone[1]), min(x1, zone[2]), min(y1, zone[3]))
    if window[0] < window[2] and window[1] < window[3]:
        yield from anchors_in(world, cell, window)


def closed_cells(
    world: Any, cache: dict[int, tuple[frozenset, frozenset]]
) -> tuple[frozenset, frozenset]:
    """The fixed bus cells and the ring cells of the world's fabric, computed once per fabric."""
    key = id(world.fabric)
    if key not in cache:
        regions = world.fabric.regions
        fixed = regions[FIXED].cells() if FIXED in regions else frozenset()
        ring = regions[RING].cells() if RING in regions else frozenset()
        cache.clear()
        cache[key] = (fixed, ring)
    return cache[key]


def wired_pins(world: Any, cache: dict[int, dict]) -> dict[str, frozenset[str]]:
    """Per cell, the pins some net carries; computed once per netlist."""
    key = id(world.netlist)
    if key not in cache:
        pins: dict[str, set[str]] = {}
        for net in world.netlist.nets.values():
            for ref in net.pins():
                pins.setdefault(ref.cell, set()).add(ref.pin)
        cache.clear()
        cache[key] = {c: frozenset(p) for c, p in pins.items()}
    return cache[key]


def approach_fault(
    world: Any,
    cell: Cell,
    placement: Placement,
    rect: Rect,
    closed: tuple,
    wired: frozenset[str],
) -> str | None:
    """Every wired pin keeps a port whose attach cell lies open with a neighbour its wire can arrive through; a routed pin keeps the port in use."""
    fp = world.footprint_of(cell.id)
    if fp is None or not wired:
        return None
    fixed, ring = closed
    options: dict[str, list[tuple[tuple[int, int], str]]] = {}
    for pin in world.netlist.pins_of(cell.id):
        if not pin.ports or pin.id not in wired:
            continue
        routed = world.routed_port(cell.id, pin.id)
        for port_id in (routed,) if routed is not None else pin.ports:
            port = fp.port(port_id)
            if port is None:
                continue
            ax, ay = attach_cell(
                fp.width, fp.height, port.side, port.offset, placement.rot
            )
            options.setdefault(pin.id, []).append(
                ((placement.x + ax, placement.y + ay), pin.carrier)
            )
    taken = {xy for found in options.values() for xy, _ in found}
    shut_belt = fixed | ring
    for pin_id, found in options.items():
        faults = [
            _approach_fault(
                world, rect, fixed if carrier == PIPE else shut_belt, xy, taken
            )
            for xy, carrier in found
        ]
        if all(fault is not None for fault in faults):
            return f"port {pin_id} {faults[0]}"
    return None


def _approach_fault(
    world: Any, rect: Rect, shut: frozenset, xy: tuple[int, int], taken: set
) -> str | None:
    """Why an attach cell cannot receive a wire: closed, or without a free neighbour outside the footprint."""
    x, y = xy
    if not world.in_grid(xy) or xy in shut:
        return "attaches on a closed cell"
    for near in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
        if rect[0] <= near[0] < rect[2] and rect[1] <= near[1] < rect[3]:
            continue
        if world.in_grid(near) and near not in taken and near not in shut:
            return None
    return "keeps no cell its wire can arrive through"


class EndfieldBoundaries(DefaultBoundaries):
    def __init__(self) -> None:
        self.closed: dict[int, tuple[frozenset, frozenset]] = {}
        self.wired: dict[int, dict[str, frozenset[str]]] = {}

    def anchors(self, world: Any, cell: Cell) -> Iterable[Anchor]:
        area = area_rect(world.fabric)
        kind = cell.constraint.kind
        if kind == "edge":
            return edge_anchors(world, cell)
        if kind == "slot":
            return slot_anchors(world, cell)
        if kind in (SEAT, CLUSTER) or cell.group == BUS_GROUP:
            return bus_anchors(world, cell, area)
        if kind == ZONE_KIND or (cell.group or "").startswith(ZONE_KIND):
            return zone_anchors(world, cell, area)
        return anchors_in(world, cell, area)

    def legal(self, world: Any, placement: Placement) -> Refusal | None:
        cell = world.netlist.cells[placement.cell]
        rect = rect_of(world, cell.id, placement)
        detail = self.fault(world, cell, placement, rect)
        if detail is None:
            return None
        return Refusal(stage="legal", subject=f"cell:{cell.id}", detail=detail)

    def fault(
        self, world: Any, cell: Cell, placement: Placement, rect: Rect
    ) -> str | None:
        """What the game refuses about this placement, or None."""
        if not inside(rect, area_rect(world.fabric)):
            return "outside the Core AIC Area"
        blocked = approach_fault(
            world,
            cell,
            placement,
            rect,
            closed_cells(world, self.closed),
            wired_pins(world, self.wired).get(cell.id, frozenset()),
        )
        if blocked is not None:
            return blocked
        anchor = Anchor(x=placement.x, y=placement.y, rot=placement.rot)
        kind = cell.constraint.kind
        if kind == "edge" and anchor not in set(edge_anchors(world, cell)):
            return "an outside input stands on the border with its pipe leaving inward"
        if kind == "slot" and anchor not in set(slot_anchors(world, cell)):
            return "a Valley IV brick stands on a slot of the fixed bus"
        if cell.group == BUS_GROUP:
            return self.bus_fault(world, cell, placement, rect)
        if cell.group is not None and cell.group.startswith(ZONE_KIND):
            return self.zone_fault(world, cell, placement, rect)
        return None

    def bus_fault(
        self, world: Any, cell: Cell, placement: Placement, rect: Rect
    ) -> str | None:
        mates = placed_members(world, BUS_GROUP, cell.id)
        parts = [(c, p) for c, p in mates if c.kind == PART_KIND]
        part_rects = [rect_of(world, c.id, p) for c, p in parts]
        part_cells = {
            (x, y)
            for x0, y0, x1, y1 in part_rects
            for y in range(y0, y1)
            for x in range(x0, x1)
        }
        if cell.kind == PART_KIND:
            bricks = [(c, p) for c, p in mates if c.kind in BRICK_KINDS]
            backs = {c for cell_b, p in bricks for c in back_cells(world, cell_b, p)}
            covers_back = any(
                rect[0] <= x < rect[2] and rect[1] <= y < rect[3] for x, y in backs
            )
            if (
                parts
                and not any(touching(rect, r) for r in part_rects)
                and not covers_back
            ):
                return "a bus part touches the cluster (DEP-09, DEP-17)"
            return None
        if cell.kind in BRICK_KINDS and cell.constraint.kind != "slot":
            if not part_cells:
                return "a brick seats on a bus part, so the bus comes first (DEP-06)"
            if not seated(world, cell, placement, part_cells):
                return "a brick's back face seats on a bus part (DEP-06, DEP-18)"
        return None

    def zone_fault(
        self, world: Any, cell: Cell, placement: Placement, rect: Rect
    ) -> str | None:
        mates = placed_members(world, cell.group or "", cell.id)
        if cell.kind == ZONE_KIND:
            zone = zone_rect(world, cell.id, placement)
            for member, other in mates:
                if not inside(rect_of(world, member.id, other), zone):
                    return f"the zone must hold {member.id} whole (ENV-02)"
            for other_id, other in world.placements.items():
                other_cell = world.netlist.cells[other_id]
                if (
                    other_cell.kind == ZONE_KIND
                    and other_id != cell.id
                    and overlaps(zone, zone_rect(world, other_id, other))
                ):
                    return f"zones of {cell.id} and {other_id} overlap (ENV-02)"
            return None
        for unit, other in mates:
            if unit.kind == ZONE_KIND and not inside(
                rect, zone_rect(world, unit.id, other)
            ):
                return f"{cell.id} must lie whole inside the zone of {unit.id} (ENV-02)"
        return None

    def crossing_region(self, carrier: str, region: str) -> bool:
        if region == RING:
            return carrier == PIPE
        return region != FIXED


__all__ = [
    "BRICK_KINDS",
    "BUS_GROUP",
    "BUS_PORT",
    "CLUSTER",
    "PART_KIND",
    "SEAT",
    "ZONE_KIND",
    "ZONE_REACH",
    "EndfieldBoundaries",
    "back_cells",
    "edge_anchors",
    "inside",
    "overlaps",
    "rect_of",
    "seated",
    "slot_anchors",
    "touching",
    "turn",
    "zone_rect",
]
