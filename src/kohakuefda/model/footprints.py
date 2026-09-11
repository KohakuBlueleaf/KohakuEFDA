"""Footprints of placed machines and units in grid cells."""

from kohakuefda.model.dataset import Dataset
from kohakuefda.model.geometry import rotated_size
from kohakuefda.model.layout import Cell, Placed, Unit


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


def inside(cell: Cell, width: int, height: int) -> bool:
    return 0 <= cell[0] < width and 0 <= cell[1] < height
