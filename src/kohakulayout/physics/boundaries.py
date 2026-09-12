"""Stage 3 defaults: free anchors anywhere in the build region, nothing extra is illegal."""

from collections.abc import Iterable
from typing import Any

from kohakulayout.ir import Cell, Footprint, Net, Placement, Refusal
from kohakulayout.ir.geometry import XY, footprint_cells
from kohakulayout.physics.protocol import Anchor


def free_anchors(world: Any, cell: Cell) -> Iterable[Anchor]:
    """Every rotation and position where the cell's footprint fits inside the build region."""
    fp = world.footprint_of(cell.id)
    if fp is None:
        return
    build = world.build_cells
    for rot in fp.rotations:
        for y in range(world.fabric.height):
            for x in range(world.fabric.width):
                if all(
                    c in build for c in footprint_cells(x, y, fp.width, fp.height, rot)
                ):
                    yield Anchor(x=x, y=y, rot=rot)


def edge_cells(world: Any, side: str) -> tuple[XY, ...]:
    """The grid cells along one side, in reading order."""
    w, h = world.fabric.width, world.fabric.height
    if side == "N":
        return tuple((x, 0) for x in range(w))
    if side == "S":
        return tuple((x, h - 1) for x in range(w))
    if side == "W":
        return tuple((0, y) for y in range(h))
    return tuple((w - 1, y) for y in range(h))


class DefaultBoundaries:
    def anchors(self, world: Any, cell: Cell) -> Iterable[Anchor]:
        return free_anchors(world, cell)

    def anchor_rows(self, world: Any, cell: Cell) -> Iterable[tuple[int, int, int]]:
        """The anchors as ``(x, y, rot)`` rows, in ``anchors``' order."""
        return ((a.x, a.y, a.rot) for a in self.anchors(world, cell))

    def legal(self, world: Any, placement: Placement) -> Refusal | None:
        return None

    def outside(self, world: Any, net: Net) -> tuple[XY, ...]:
        if net.outside is None:
            return ()
        return edge_cells(world, net.outside)

    def crossing_region(self, carrier: str, region: str) -> bool:
        return region == "build"

    def unit_region(self, unit: Footprint, region: str) -> bool:
        return True
