"""Wire paths as moves, cells and waypoints, and back again."""

from itertools import pairwise

from kohakulayout.errors import TextError
from kohakulayout.ir.geometry import OUTWARD, XY

DELTA = {side: delta for side, delta in OUTWARD.items()}
SIDE_OF = {delta: side for side, delta in OUTWARD.items()}


def cells_from_moves(start: XY, moves: list) -> tuple[XY, ...]:
    """The cells a path visits from ``start`` through ``("move", side, n)`` and ``("cell", xy)`` items."""
    cells = [start]
    x, y = start
    for item in moves:
        if item[0] == "move":
            dx, dy = DELTA[item[1]]
            for _ in range(item[2]):
                x, y = x + dx, y + dy
                cells.append((x, y))
        else:
            tx, ty = item[1]
            if tx != x and ty != y:
                raise TextError(f"waypoint @{tx},{ty} is not in line with ({x},{y})")
            dx = (tx > x) - (tx < x)
            dy = (ty > y) - (ty < y)
            while (x, y) != (tx, ty):
                x, y = x + dx, y + dy
                cells.append((x, y))
    return tuple(cells)


def moves_from_cells(cells: tuple[XY, ...]) -> list[str]:
    """Run-length moves such as ``E5 S2`` for a contiguous path; the first cell is implied."""
    out: list[str] = []
    run_side = ""
    run = 0
    for (ax, ay), (bx, by) in pairwise(cells):
        side = SIDE_OF[(bx - ax, by - ay)]
        if side == run_side:
            run += 1
        else:
            if run:
                out.append(f"{run_side}{run}")
            run_side, run = side, 1
    if run:
        out.append(f"{run_side}{run}")
    return out


def parse_move(token: str) -> tuple:
    return ("move", token[0], int(token[1:]))
