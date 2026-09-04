"""Depot access as a placement resource: where depot bricks may stand and how many.

A brick (Depot Loader or Unloader, 3×1) must touch a Depot Bus part with the face opposite
its port (game-knowledge DEP-05, DEP-06). In Wuling the bus is laid by the player: a 4×4 port
and 4×8 sections, active when their edges touch (DEP-08, DEP-09); the bricks a chain of parts
can seat is what its perimeter holds, three cells per brick along the long sides and one brick
per end. In Valley IV the bus is fixed in the ring around the area, so bricks stand on the
area's border cells along each segment (DEP-11, DEP-12); ``fixed_slots`` lists those cells in
square coordinates with the side the bus is on.
"""

from kohakuefda.model.basement import BusSegment, LaidBus
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.geometry import Edge, Rotation, rotate_edge
from kohakuefda.model.items import Phase
from kohakuefda.model.machines import Machine
from kohakuefda.model.scenario import BasementRef

BRICK = 3
PORT_LENGTH = 4
SECTION_LENGTH = 8
BUS_PORT = "log_hongs_bus_source"
BUS_SECTION = "log_hongs_bus"
OPPOSITE = {Edge.N: Edge.S, Edge.S: Edge.N, Edge.E: Edge.W, Edge.W: Edge.E}


class Slot:
    """A brick position: its anchor cell and the side on which the bus lies."""

    def __init__(self, x: int, y: int, side: Edge) -> None:
        self.x = x
        self.y = y
        self.side = side

    def size(self) -> tuple[int, int]:
        return (BRICK, 1) if self.side in (Edge.N, Edge.S) else (1, BRICK)

    def cells(self) -> list[tuple[int, int]]:
        w, d = self.size()
        return [(self.x + i, self.y + j) for j in range(d) for i in range(w)]


def brick_rotation(machine: Machine, side: Edge) -> Rotation:
    """The rotation that turns the brick's port away from the bus on ``side``."""
    port = machine.ports[0]
    return next(
        r for r in (0, 90, 180, 270) if rotate_edge(port.edge, r) is OPPOSITE[side]
    )


def chain_capacity(ports: int, sections: int) -> int:
    """Bricks a straight chain of ``ports`` and ``sections`` seats: three cells per brick
    along both long sides plus one brick at each end."""
    length = PORT_LENGTH * ports + SECTION_LENGTH * sections
    return 2 * (length // BRICK) + 2 if length else 0


def sections_needed(bricks: int, ports: int = 1) -> int:
    """The fewest sections whose chain with ``ports`` seats ``bricks``."""
    sections = 0
    while chain_capacity(ports, sections) < bricks:
        sections += 1
    return sections


def laid_limits(bus: LaidBus, depot_level: int) -> tuple[int, int]:
    """Ports and sections a Wuling depot level allows (DEP-10)."""
    known = [lv for lv in bus.sections_by_level if lv <= depot_level]
    if not known:
        return 0, 0
    level = max(known)
    return bus.ports_by_level.get(level, 1), bus.sections_by_level[level]


def _runs(segments: list[BusSegment]) -> list[tuple[int, int, int, Edge]]:
    """Adjoining segments merged into runs: ``(face, start, length, side)``.

    A brick seats on the cells of a run, not of one segment, so two segments that meet leave no
    gap between the bricks on them (DEP-18). ``face`` is the row or column the bricks stand on,
    inside the area.
    """
    lines: dict[tuple[int, Edge, bool], list[tuple[int, int]]] = {}
    for segment in segments:
        flat = segment.depth < segment.width
        if flat:
            face = segment.y + segment.depth if segment.y < 0 else segment.y - 1
            side = Edge.N if segment.y < 0 else Edge.S
            span = (segment.x, segment.x + segment.width)
        else:
            face = segment.x + segment.width if segment.x < 0 else segment.x - 1
            side = Edge.W if segment.x < 0 else Edge.E
            span = (segment.y, segment.y + segment.depth)
        lines.setdefault((face, side, flat), []).append(span)
    out: list[tuple[int, int, int, Edge]] = []
    for (face, side, _), spans in lines.items():
        start, stop = None, None
        for begin, end in sorted(spans):
            if start is None:
                start, stop = begin, end
            elif begin <= stop:
                stop = max(stop, end)
            else:
                out.append((face, start, stop - start, side))
                start, stop = begin, end
        if start is not None:
            out.append((face, start, stop - start, side))
    return out


def run_capacity(length: int) -> int:
    """Bricks a run of ``length`` cells seats, three cells apart (DEP-18)."""
    return length // BRICK


def fixed_slots(dataset: Dataset, basement: BasementRef) -> list[Slot]:
    """Brick slots along a Valley IV bus in square coordinates; empty for a laid bus."""
    entry = dataset.basements.get(basement.basement_id)
    if entry is None or entry.depot.kind != "fixed":
        return []
    slots: list[Slot] = []
    for face, start, length, side in _runs(
        list(entry.depot.segments(basement.depot_level))
    ):
        flat = side in (Edge.N, Edge.S)
        for step in range(run_capacity(length)):
            along = start + step * BRICK
            slots.append(Slot(along, face, side) if flat else Slot(face, along, side))
    return slots


def io_budget(dataset: Dataset, basement: BasementRef) -> int | None:
    """Bricks the depot level allows, or ``None`` when the basement is unknown."""
    entry = dataset.basements.get(basement.basement_id)
    if entry is None:
        return None
    if entry.depot.kind == "fixed":
        return len(fixed_slots(dataset, basement))
    ports, sections = laid_limits(entry.depot, basement.depot_level)
    return chain_capacity(ports, sections)


def via_depot_ok(
    dataset: Dataset, item_id: str, source_kinds: set[str], sink_kinds: set[str]
) -> bool:
    """A solid item flowing between production machines may be carried by the depot."""
    return (
        dataset.items[item_id].phase is Phase.SOLID
        and "recipe" in source_kinds
        and "recipe" in sink_kinds
    )
