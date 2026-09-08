"""Stage 3 for gates: the ``edge`` constraint anchors a cell on one side of the board."""

from collections.abc import Iterable
from typing import Any

from kohakulayout.ir import Cell, Placement, Refusal
from kohakulayout.ir.geometry import rotate_size
from kohakulayout.physics import Anchor, DefaultBoundaries, free_anchors

PACK = "gates"


def edge_side(cell: Cell) -> str | None:
    if cell.constraint.kind != "edge":
        return None
    return cell.constraint.attrs.get(PACK, {}).get("side")


def touches(world: Any, placement: Placement, side: str) -> bool:
    fp = world.footprint_of(placement.cell)
    if fp is None:
        return False
    rw, rh = rotate_size(fp.width, fp.height, placement.rot)
    if side == "W":
        return placement.x == 0
    if side == "E":
        return placement.x + rw == world.fabric.width
    if side == "N":
        return placement.y == 0
    return placement.y + rh == world.fabric.height


class GatesBoundaries(DefaultBoundaries):
    def anchors(self, world: Any, cell: Cell) -> Iterable[Anchor]:
        side = edge_side(cell)
        fp = world.footprint_of(cell.id)
        if side is None or fp is None:
            yield from free_anchors(world, cell)
            return
        width, height = world.fabric.width, world.fabric.height
        for rot in fp.rotations:
            rw, rh = rotate_size(fp.width, fp.height, rot)
            if side in ("W", "E"):
                x = 0 if side == "W" else width - rw
                for y in range(height - rh + 1):
                    yield Anchor(x=x, y=y, rot=rot)
            else:
                y = 0 if side == "N" else height - rh
                for x in range(width - rw + 1):
                    yield Anchor(x=x, y=y, rot=rot)

    def legal(self, world: Any, placement: Placement) -> Refusal | None:
        cell = world.netlist.cells[placement.cell]
        side = edge_side(cell)
        if side is not None and not touches(world, placement, side):
            return Refusal(
                stage="legal",
                subject=f"cell:{cell.id}",
                detail=f"must touch the {side} edge",
            )
        return None


__all__ = ["GatesBoundaries", "edge_side", "touches"]
