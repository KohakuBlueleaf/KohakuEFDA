"""World-space geometry of placed things: footprints, port cells, the cell a port faces."""

from kohakuefda.model.dataset import Dataset
from kohakuefda.model.geometry import Edge, edge_step, rotated_size
from kohakuefda.model.layout import Cell, Placed, Unit
from kohakuefda.model.logistics import LogisticsUnit
from kohakuefda.model.machines import Machine, Port


class WorldPort:
    """A port of a placed entity in world cells: the cell it sits on and the cell it faces."""

    def __init__(self, owner: str, port: Port, cell: Cell, edge: Edge) -> None:
        self.owner = owner
        self.port = port
        self.cell = cell
        self.edge = edge
        dx, dy = edge_step(edge)
        self.outside: Cell = (cell[0] + dx, cell[1] + dy)

    @property
    def direction(self) -> str:
        return self.port.direction

    @property
    def type(self) -> str:
        return self.port.type


def footprint(x: int, y: int, width: int, depth: int, rotation: int) -> list[Cell]:
    """Cells covered by a width×depth footprint anchored at (x, y) after rotation."""
    w, d = rotated_size(width, depth, rotation)
    return [(x + i, y + j) for j in range(d) for i in range(w)]


def machine_footprint(dataset: Dataset, placed: Placed) -> list[Cell]:
    machine = dataset.machines[placed.machine_id]
    return footprint(placed.x, placed.y, machine.width, machine.depth, placed.rotation)


def unit_footprint(dataset: Dataset, unit: Unit) -> list[Cell]:
    spec = dataset.logistics[unit.unit_id]
    return footprint(unit.x, unit.y, spec.width, spec.depth, unit.rotation)


def machine_ports(dataset: Dataset, placed: Placed) -> list[WorldPort]:
    machine: Machine = dataset.machines[placed.machine_id]
    return [
        WorldPort(placed.id, p, (placed.x + p.x, placed.y + p.y), p.edge)
        for p in machine.ports_at(placed.rotation)
    ]


def unit_ports(dataset: Dataset, unit: Unit) -> list[WorldPort]:
    spec: LogisticsUnit = dataset.logistics[unit.unit_id]
    return [
        WorldPort(unit.id, p, (unit.x + p.x, unit.y + p.y), p.edge)
        for p in (q.rotated(spec.width, spec.depth, unit.rotation) for q in spec.ports)
    ]


def adjacent(a: Cell, b: Cell) -> bool:
    return abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1


def inside(cell: Cell, width: int, height: int) -> bool:
    return 0 <= cell[0] < width and 0 <= cell[1] < height
