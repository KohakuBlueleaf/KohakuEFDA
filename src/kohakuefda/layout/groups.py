"""Group rules: what the game binds together and how far a placement is from obeying it.

A Depot Bus is one touching cluster reached from a Bus Port, and every brick's back face
touches a part (game-knowledge DEP-06, DEP-09). A Gas Dispersing Unit's 13×13 zone must contain
the whole footprint of every machine it serves, and zones never overlap (ENV-01, ENV-02).
``faults`` counts the rules broken, one per block or pair, so a cost can carry it.
"""

from kohakuefda.layout.coverage import overlaps, zone_rect
from kohakuefda.layout.depot_via import BUS_PORT
from kohakuefda.layout.place import Block, touching
from kohakuefda.model.cells import BUS_GROUP
from kohakuefda.model.geometry import Edge, edge_step
from kohakuefda.model.layout import Cell, Rect

OPPOSITE = {Edge.N: Edge.S, Edge.S: Edge.N, Edge.E: Edge.W, Edge.W: Edge.E}


def back_cells(block: Block) -> list[Cell]:
    """The cells a brick's back face (opposite its port) looks at."""
    key = next(iter(block.pins))
    _, edge = block.pin_world(key)
    dx, dy = edge_step(OPPOSITE[edge])
    x0, y0, x1, y1 = block.rect()
    return [
        (x + dx, y + dy)
        for x in range(x0, x1)
        for y in range(y0, y1)
        if not (x0 <= x + dx < x1 and y0 <= y + dy < y1)
    ]


def bus_faults(blocks: list[Block]) -> int:
    """Bus parts not in one touching cluster with a port, plus bricks whose back face touches
    no part. Judged only once the Bus Port stands: before it there is no cluster to be off.
    """
    parts = [b for b in blocks if b.kind == "depot"]
    bricks = [b for b in blocks if b.kind != "depot" and b.pins]
    ports = [b for b in parts if b.fragment.machine_id == BUS_PORT]
    if not ports:
        return 0
    reached = {b.id for b in ports}
    frontier = list(ports)
    while frontier:
        current = frontier.pop()
        for other in parts:
            if other.id not in reached and touching(current.rect(), other.rect()):
                reached.add(other.id)
                frontier.append(other)
    count = sum(1 for b in parts if b.id not in reached)
    part_cells: set[Cell] = set()
    for part in parts:
        part_cells.update(part.cells())
    for brick in bricks:
        if not any(c in part_cells for c in back_cells(brick)):
            count += 1
    return count


def zone_faults(blocks: list[Block]) -> int:
    """Members whose footprint leaves their unit's zone. Judged only once the Gas Dispersing
    Unit stands: before it there is no zone to be outside of."""
    unit = next((b for b in blocks if b.kind == "zone"), None)
    if unit is None:
        return 0
    zone = zone_rect((unit.x, unit.y), unit.width)
    count = 0
    for block in blocks:
        if block is unit:
            continue
        x0, y0, x1, y1 = block.rect()
        if not (zone[0] <= x0 and zone[1] <= y0 and x1 <= zone[2] and y1 <= zone[3]):
            count += 1
    return count


def zone_of(blocks: list[Block]) -> Rect | None:
    """The 13×13 a group's Gas Dispersing Unit makes, when it has one placed."""
    unit = next((b for b in blocks if b.kind == "zone"), None)
    return zone_rect((unit.x, unit.y), unit.width) if unit is not None else None


def faults(groups: dict[str, list[Block]]) -> int:
    """Every group rule the current positions break, overlapping zones included."""
    count = 0
    zones: list[Rect] = []
    for name, members in groups.items():
        if name == BUS_GROUP:
            count += bus_faults(members)
            continue
        count += zone_faults(members)
        zone = zone_of(members)
        if zone is not None:
            zones.append(zone)
    for index, first in enumerate(zones):
        count += sum(1 for other in zones[index + 1 :] if overlaps(first, other))
    return count
