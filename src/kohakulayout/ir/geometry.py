"""Grid geometry shared by every level: sides, rotations, footprint cells, port and attach cells.

Coordinates run x to the right and y downwards; a footprint is anchored at its top-left
cell; rotations are clockwise in steps of ninety degrees about that anchor.
"""

from itertools import pairwise
from typing import Literal

Side = Literal["N", "E", "S", "W"]
Rotation = Literal[0, 90, 180, 270]
XY = tuple[int, int]

SIDES: tuple[Side, ...] = ("N", "E", "S", "W")
ROTATIONS: tuple[Rotation, ...] = (0, 90, 180, 270)
OUTWARD: dict[str, XY] = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}


def rotate_size(width: int, height: int, rot: int) -> XY:
    return (width, height) if rot in (0, 180) else (height, width)


def rotate_side(side: str, rot: int) -> str:
    return SIDES[(SIDES.index(side) + rot // 90) % 4]


def rotate_point(px: int, py: int, width: int, height: int, rot: int) -> XY:
    """Where the cell ``(px, py)`` of an unrotated ``width x height`` box lands after ``rot``."""
    if rot == 0:
        return (px, py)
    if rot == 90:
        return (height - 1 - py, px)
    if rot == 180:
        return (width - 1 - px, height - 1 - py)
    return (py, width - 1 - px)


def port_cell(width: int, height: int, side: str, offset: int, rot: int) -> XY:
    """The footprint cell a port occupies, relative to the anchor, after rotation."""
    if side == "N":
        px, py = offset, 0
    elif side == "S":
        px, py = offset, height - 1
    elif side == "W":
        px, py = 0, offset
    else:
        px, py = width - 1, offset
    return rotate_point(px, py, width, height, rot)


def attach_cell(width: int, height: int, side: str, offset: int, rot: int) -> XY:
    """The outward neighbour of a port: where a wire meets it, relative to the anchor."""
    cx, cy = port_cell(width, height, side, offset, rot)
    dx, dy = OUTWARD[rotate_side(side, rot)]
    return (cx + dx, cy + dy)


def footprint_cells(
    x: int, y: int, width: int, height: int, rot: int
) -> tuple[XY, ...]:
    rw, rh = rotate_size(width, height, rot)
    return tuple((x + i, y + j) for j in range(rh) for i in range(rw))


def side_length(width: int, height: int, side: str) -> int:
    return width if side in ("N", "S") else height


def rotate_cells(
    cells: tuple[XY, ...], width: int, height: int, rot: int
) -> tuple[XY, ...]:
    """Every cell of a ``width x height`` fragment rotated about its origin."""
    return tuple(rotate_point(px, py, width, height, rot) for px, py in cells)


def bbox(cells: tuple[XY, ...] | frozenset[XY]) -> tuple[int, int, int, int]:
    """``(min_x, min_y, width, height)`` of a non-empty cell set."""
    xs = [c[0] for c in cells]
    ys = [c[1] for c in cells]
    return (min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1)


def contiguous(cells: tuple[XY, ...]) -> bool:
    """True when consecutive cells are 4-neighbours and no cell repeats."""
    if len(set(cells)) != len(cells):
        return False
    for (ax, ay), (bx, by) in pairwise(cells):
        if abs(ax - bx) + abs(ay - by) != 1:
            return False
    return True


def connected(cells: frozenset[XY]) -> bool:
    """True when the cell set is one 4-connected component."""
    if not cells:
        return True
    start = next(iter(cells))
    seen = {start}
    frontier = [start]
    while frontier:
        x, y = frontier.pop()
        for dx, dy in OUTWARD.values():
            nxt = (x + dx, y + dy)
            if nxt in cells and nxt not in seen:
                seen.add(nxt)
                frontier.append(nxt)
    return len(seen) == len(cells)
