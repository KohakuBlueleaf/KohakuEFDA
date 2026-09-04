"""Two-layer occupancy grid: ground (machines, belts, belt units) and sky (pipes, pipe units)."""

import numpy as np

from kohakuefda.layout.geometry import machine_footprint, unit_footprint
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.layout import Cell, Layout
from kohakuefda.model.machines import GROUND, SKY

FREE = 0


class Occupancy:
    """Who occupies each cell on each layer; ``0`` is free, otherwise an entity index + 1."""

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.grid = np.zeros((2, height, width), dtype=np.int32)
        self.names: list[str] = []
        self.conflicts: list[tuple[int, Cell, str, str]] = []

    def _index(self, name: str) -> int:
        self.names.append(name)
        return len(self.names)

    def claim(self, name: str, cells: list[Cell], layers: tuple[int, ...]) -> None:
        """Mark ``cells`` on ``layers`` for ``name``; out-of-bounds and overlaps are recorded."""
        index = self._index(name)
        for x, y in cells:
            if not (0 <= x < self.width and 0 <= y < self.height):
                self.conflicts.append((-1, (x, y), name, "out of bounds"))
                continue
            for layer in layers:
                current = self.grid[layer, y, x]
                if current != FREE:
                    self.conflicts.append(
                        (layer, (x, y), name, self.names[current - 1])
                    )
                else:
                    self.grid[layer, y, x] = index

    def occupant(self, layer: int, cell: Cell) -> str | None:
        x, y = cell
        if not (0 <= x < self.width and 0 <= y < self.height):
            return None
        value = self.grid[layer, y, x]
        return None if value == FREE else self.names[value - 1]

    def is_free(self, layer: int, cell: Cell) -> bool:
        x, y = cell
        return (
            0 <= x < self.width
            and 0 <= y < self.height
            and self.grid[layer, y, x] == FREE
        )


def occupancy_of(dataset: Dataset, layout: Layout) -> Occupancy:
    """Occupancy of a whole layout: machines block both layers, belts ground, pipes and
    outside inputs sky."""
    occ = Occupancy(layout.width, layout.height)
    for placed in layout.machines:
        occ.claim(placed.id, machine_footprint(dataset, placed), (GROUND, SKY))
    for unit in layout.units:
        spec = dataset.logistics[unit.unit_id]
        layers = (GROUND, SKY) if spec.kind.startswith("pipe") else (GROUND,)
        occ.claim(unit.id, unit_footprint(dataset, unit), layers)
    for segment in layout.segments:
        layer = SKY if segment.kind == "pipe" else GROUND
        occ.claim(segment.id, segment.cells, (layer,))
    for entry in layout.entries:
        occ.claim(entry.owner, [entry.cell], (SKY,))
    return occ
