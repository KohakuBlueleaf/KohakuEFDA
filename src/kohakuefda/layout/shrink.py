"""Taking the room back out of a layout that already stands.

The spread leaves every machine alone in a lattice square with a corridor round it, which is what
makes it always come out whole and what makes it far larger than it needs to be. Shrinking only
ever *removes* space: a line nothing stands on is deleted and everything past it slides in, or a
whole side is pressed toward a wall. Each proposal is a complete layout, rebuilt and rewired from
scratch, and it is kept only when it still stands whole and is smaller; otherwise the layout that
was there comes straight back.

Nothing here can strand a machine or a lane, because nothing here makes room — the worst a round
can do is fail to find an improvement and stop.
"""

import logging

from kohakuefda.layout.site import Site
from kohakuefda.layout.spread import Spread
from kohakuefda.model.layout import Cell, Rect

log = logging.getLogger(__name__)
PINNED = ("slot", "edge")
SIDES = ((0, -1), (1, -1), (0, 1), (1, 1))
Size = tuple[int, int]


def inside(area: Rect, cell: Cell) -> bool:
    return area[0] <= cell[0] < area[2] and area[1] <= cell[1] < area[3]


class Shrink:
    """Presses and carves a standing layout; ``run`` returns whether it got any smaller."""

    def __init__(self, site: Site, spread: Spread, params: dict) -> None:
        self.site = site
        self.spread = spread
        self.rounds = max(0, int(params["shrink_rounds"]))

    # ---- what counts as smaller -----------------------------------------

    def measure(self) -> Size:
        """The rectangle the layout needs, then its lane cells: area first because that is what
        the basement charges for, lanes second because two layouts of the same area are not
        equally good and the shorter belt is the one the player wants."""
        x0, y0, x1, y1 = self.site.bbox()
        return ((x1 - x0) * (y1 - y0), self.site.wire_cells())

    def apply(self, anchors: dict[str, tuple[int, int, int]], before: Size) -> bool:
        """Rebuild the whole layout at these anchors and keep it only if it still stands whole
        and is smaller than ``before``."""
        site = self.site
        state = site.snapshot()
        if (
            self.spread.rebuild(anchors, self.spread.laid)
            and not site.unplaced()
            and not site.unrouted()
            and self.measure() < before
        ):
            return True
        site.restore(state)
        return False

    # ---- the two moves ---------------------------------------------------

    def empty_lines(self) -> tuple[list[int], list[int]]:
        """Columns and rows of the layout's rectangle that no machine stands on. A lane may
        cross them: deleting one shortens the lane instead of breaking it."""
        site = self.site
        x0, y0, x1, y1 = site.bbox()
        standing = {cell for cells in site.cells_of.values() for cell in cells}
        columns = sorted({x for x in range(x0, x1)} - {c[0] for c in standing})
        rows = sorted({y for y in range(y0, y1)} - {c[1] for c in standing})
        return columns, rows

    def carve(self, before: Size) -> bool:
        """Delete one line nothing stands on, pulling everything past it in by a cell."""
        columns, rows = self.empty_lines()
        for axis, lines in ((0, columns), (1, rows)):
            for line in reversed(lines):
                anchors = {}
                for block_id, (x, y, rotation) in self.site.placed.items():
                    if self.site.blocks[block_id].constraint in PINNED:
                        anchors[block_id] = (x, y, rotation)
                    elif axis == 0:
                        anchors[block_id] = (x - 1 if x > line else x, y, rotation)
                    else:
                        anchors[block_id] = (x, y - 1 if y > line else y, rotation)
                if self.apply(anchors, before):
                    return True
        return False

    def press(self, axis: int, step: int, before: Size) -> bool:
        """Slide every machine as far as it will go along one axis, nearest the wall first.

        A machine stops at the first cell another has already claimed, so the sweep never
        overlaps anything; whether the lanes still run is settled the only way anything is
        here, by routing them.
        """
        site = self.site
        order = sorted(site.placed, key=lambda i: site.placed[i][axis] * -step)
        taken: set[Cell] = set()
        for block_id in order:
            if site.blocks[block_id].constraint in PINNED:
                taken |= set(site.cells_of[block_id])
        anchors: dict[str, tuple[int, int, int]] = {}
        for block_id in order:
            x, y, rotation = site.placed[block_id]
            if site.blocks[block_id].constraint in PINNED:
                anchors[block_id] = (x, y, rotation)
                continue
            cells = list(site.cells_of[block_id])
            while True:
                moved = [
                    (c[0] + step, c[1]) if axis == 0 else (c[0], c[1] + step)
                    for c in cells
                ]
                if any(not inside(site.area, c) or c in taken for c in moved):
                    break
                cells = moved
                x, y = (x + step, y) if axis == 0 else (x, y + step)
            taken |= set(cells)
            anchors[block_id] = (x, y, rotation)
        return self.apply(anchors, before)

    def nudge(self, before: Size) -> bool:
        """Move one machine one cell toward what it is wired to.

        A press moves everything at once and a layout that dense often will not route, so it
        is rejected whole; one machine at a time only disturbs its own lanes, and the cell it
        gives back is a cell the rectangle no longer has to hold.
        """
        site = self.site
        movable = [i for i in site.placed if site.blocks[i].constraint not in PINNED]
        for block_id in movable:
            x, y, rotation = site.placed[block_id]
            for dx, dy in self.toward(block_id):
                state = site.snapshot()
                site.remove(block_id)
                if (
                    site.place(block_id, x + dx, y + dy, rotation)
                    and not site.unrouted()
                    and self.measure() < before
                ):
                    return True
                site.restore(state)
        return False

    def toward(self, block_id: str) -> list[Cell]:
        """The single steps that take a machine nearer the machines it exchanges with, the
        one that closes the most distance first."""
        site = self.site
        x, y, _ = site.placed[block_id]
        partners = [
            (site.placed[other.id][0], site.placed[other.id][1])
            for wire in site.touching[block_id]
            for other in (
                (
                    site.owner[wire.sink]
                    if site.owner[wire.source].id == block_id
                    else site.owner[wire.source]
                ),
            )
            if other.id in site.placed and other.id != block_id
        ]
        steps = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        if not partners:
            return steps
        return sorted(
            steps,
            key=lambda s: sum(
                abs(x + s[0] - px) + abs(y + s[1] - py) for px, py in partners
            ),
        )

    # ---- the pass --------------------------------------------------------

    def run(self) -> bool:
        """Carve, press and nudge until none of them makes the layout smaller."""
        site = self.site
        started = self.measure()
        for round_index in range(self.rounds):
            before = self.measure()
            if (
                not self.carve(before)
                and not any(
                    self.press(axis, step, self.measure()) for axis, step in SIDES
                )
                and not self.nudge(self.measure())
            ):
                log.debug("nothing left to take out", rounds=round_index)
                break
        after = self.measure()
        x0, y0, x1, y1 = site.bbox()
        log.info(
            "layout shrunk",
            size=f"{x1 - x0}x{y1 - y0}",
            area=f"{started[0]} to {after[0]}",
            wires=f"{started[1]} to {after[1]}",
        )
        return after < started
