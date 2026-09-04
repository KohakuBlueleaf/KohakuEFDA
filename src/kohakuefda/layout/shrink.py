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
import math
import random

from kohakuefda.layout.site import Site
from kohakuefda.layout.spread import Spread
from kohakuefda.model.control import CancelledError
from kohakuefda.model.layout import Cell, Rect
from kohakuefda.util.progress import Ticker

log = logging.getLogger(__name__)
PINNED = ("slot", "edge")
SIDES = ((0, -1), (1, -1), (0, 1), (1, 1))
Size = tuple[int, int]


def inside(area: Rect, cell: Cell) -> bool:
    return area[0] <= cell[0] < area[2] and area[1] <= cell[1] < area[3]


class Shrink:
    """Presses and carves a standing layout; ``run`` returns whether it got any smaller."""

    def __init__(
        self,
        site: Site,
        spread: Spread,
        params: dict,
        observe=None,
        cancelled=None,
    ) -> None:
        self.site = site
        self.spread = spread
        self.params = params
        self.observe = observe
        self.cancelled = cancelled
        self.rounds = max(0, int(params["shrink_rounds"]))
        self.walk = max(0, int(params["shrink_walk"]))
        self.heat = max(1e-9, float(params["shrink_heat"]))
        self.spin = min(1.0, max(0.0, float(params["shrink_spin"])))
        self.rng = random.Random(int(params["seed"]))

    def stop(self) -> bool:
        """Whether the caller has asked for the run to end."""
        return self.cancelled is not None and self.cancelled()

    def show(self, kind: str) -> None:
        """Hand a watcher the layout as it stands, so a squeeze is not a silent wait."""
        if self.observe is not None:
            self.observe(self.spread.frame(kind))

    # ---- what counts as smaller -----------------------------------------

    def measure(self) -> Size:
        """The rectangle the layout needs with its pylons standing, then its lane cells.

        Area first because that is what the basement charges for, lanes second because two
        layouts of the same area are not equally good. The pylons are part of it: an
        arrangement that is tighter until its pylon has to stand further out is not tighter,
        and a walk judged without them wanders off toward layouts that grow when built.
        """
        site = self.site
        size = site.dataset.machines[site.pylon.machine_id].width
        cells = set(site.occupied())
        for spot in site.pylons()[0]:
            cells.update(
                (spot[0] + dx, spot[1] + dy) for dy in range(size) for dx in range(size)
            )
        return self.box(cells)

    def rough(self) -> Size:
        """The same measure without covering the layout in pylons.

        Finding where the pylons go is a cover over every machine, and a squeeze asks whether
        a layout is smaller once per machine per direction. Paying for the cover on every one
        of those made a squeeze that took a moment take twenty seconds, so it is asked only of
        the arrangements that are already smaller without it.
        """
        return self.box(set(self.site.occupied()))

    def box(self, cells: set[Cell]) -> Size:
        """The rectangle those cells need inside the area, then the layout's lane cells."""
        x0, y0, x1, y1 = self.site.area
        inside = [c for c in cells if x0 <= c[0] < x1 and y0 <= c[1] < y1]
        if not inside:
            return (0, 0)
        xs = [c[0] for c in inside]
        ys = [c[1] for c in inside]
        return (
            (max(xs) - min(xs) + 1) * (max(ys) - min(ys) + 1),
            self.site.wire_cells(),
        )

    def smaller(self, before: Size, coarse: Size) -> bool:
        """Whether the layout now is smaller, the cheap question asked first.

        Pylons only ever grow the rectangle, so an arrangement whose machines and lanes need
        more room than they did is not going to win once they are added.
        """
        if self.rough() > coarse:
            return False
        return self.measure() < before

    def apply(
        self, anchors: dict[str, tuple[int, int, int]], before: Size, coarse: Size
    ) -> bool:
        """Rebuild the whole layout at these anchors and keep it only if it still stands whole
        and is smaller than ``before``."""
        site = self.site
        state = site.snapshot()
        if (
            self.spread.rebuild(anchors, self.spread.laid)
            and not site.unplaced()
            and not site.unrouted()
            and self.smaller(before, coarse)
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

    def carve(self, before: Size, coarse: Size) -> bool:
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
                if self.apply(anchors, before, coarse):
                    return True
        return False

    def press(self, axis: int, step: int, before: Size, coarse: Size) -> bool:
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
        return self.apply(anchors, before, coarse)

    def nudge(self, before: Size, coarse: Size) -> bool:
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
                    and self.smaller(before, coarse)
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

    def turn(self, before: Size, coarse: Size) -> bool:
        """One machine turned where it stands, if it leaves the layout smaller."""
        site = self.site
        movable = [i for i in site.placed if site.blocks[i].constraint not in PINNED]
        for block_id in movable:
            x, y, rotation = site.placed[block_id]
            for turned in (90, 180, 270):
                state = site.snapshot()
                site.remove(block_id)
                if (
                    site.place(block_id, x, y, (rotation + turned) % 360)
                    and not site.unrouted()
                    and self.smaller(before, coarse)
                ):
                    return True
                site.restore(state)
        return False

    def stir(self, movable: list[str]) -> bool:
        """One machine picked at random, stepped a cell or turned where it stands.

        The squeeze scans in a fixed order and takes the first move that helps, which is what
        makes it settle; a walk that proposed the same way would offer the same machine every
        step and go nowhere. Whether the layout still stands is settled by rebuilding it.
        """
        site = self.site
        block_id = self.rng.choice(movable)
        x, y, rotation = site.placed[block_id]
        if self.rng.random() < self.spin:
            spot = (x, y, (rotation + self.rng.choice((90, 180, 270))) % 360)
        else:
            dx, dy = self.rng.choice(((1, 0), (-1, 0), (0, 1), (0, -1)))
            spot = (x + dx, y + dy, rotation)
        state = site.snapshot()
        site.remove(block_id)
        if site.place(block_id, *spot) and not site.unrouted():
            return True
        site.restore(state)
        return False

    def wander(self) -> bool:
        """Anneal the finished layout: the same kind of move, but a worse one taken now and then.

        Carving, pressing and nudging each take the first improvement they find and stop at the
        first arrangement none of them improves. Letting the walk accept a slightly larger
        layout sometimes is what gets it out of that, and every state it passes through is a
        whole routed layout, so the worst it can do is give back the one it started from.
        """
        site = self.site
        movable = [i for i in site.placed if site.blocks[i].constraint not in PINNED]
        if not movable:
            return False
        current = self.rough()
        best, mark = self.measure(), current
        kept = site.snapshot()
        moved = False
        ticker = Ticker(self.walk, "walk")
        for step in range(self.walk):
            if self.stop():
                raise CancelledError("cancelled")
            temperature = self.heat * (1.0 - step / self.walk) + 1e-9
            state = site.snapshot()
            if not self.stir(movable):
                site.restore(state)
                ticker.tick(step + 1, f"area {best[0]}")
                continue
            after = self.rough()
            delta = (after[0] - current[0]) + 0.25 * (after[1] - current[1])
            if delta <= 0 or self.rng.random() < math.exp(-delta / temperature):
                current = after
                if after <= mark and self.measure() < best:
                    best, mark = self.measure(), after
                    kept, moved = site.snapshot(), True
                    self.show("improve")
            else:
                site.restore(state)
            ticker.tick(step + 1, f"area {best[0]}")
        ticker.done()
        site.restore(kept)
        return moved

    def settle(self) -> None:
        """Carve, press and nudge until none of them makes the layout smaller."""
        for round_index in range(self.rounds):
            if self.stop():
                raise CancelledError("cancelled")
            before = self.measure()
            coarse = self.rough()
            if (
                not self.carve(before, coarse)
                and not any(
                    self.press(axis, step, before, coarse) for axis, step in SIDES
                )
                and not self.nudge(before, coarse)
                and not self.turn(before, coarse)
            ):
                log.debug("nothing left to take out", rounds=round_index)
                return
            self.show("improve")

    def run(self) -> bool:
        """Settle the layout, walk it out of that corner, then settle whatever the walk found."""
        site = self.site
        started = self.measure()
        self.settle()
        if self.walk and self.wander():
            self.settle()
        after = self.measure()
        x0, y0, x1, y1 = site.bbox()
        log.info(
            "layout shrunk",
            size=f"{x1 - x0}x{y1 - y0}",
            area=f"{started[0]} to {after[0]}",
            wires=f"{started[1]} to {after[1]}",
        )
        return after < started
