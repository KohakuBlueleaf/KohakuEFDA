"""A layout with every machine placed and every wire routed, or nothing.

Machines go into the squares of a lattice whose step is the widest of them plus a pylon, so each
one stands alone with a corridor round it and a lane can always reach the next square. They are
taken in the order the flow visits them, each chain walked to its end, and the squares in a
serpentine, so a machine lands beside the one that feeds it and the walk turns back on itself
rather than jumping home.

Nothing here is searched. One machine is one step -- it stands, its lanes are routed where it
stands, a watcher is told and the cancel is answered -- and room is given rather than looked
for: the corridor widens and the flow is walked from either end until a pass comes out whole,
and a machine the lattice could not seat is seated first on the next pass. What comes out is
legal, not small; the placement walk that follows is what makes it small.
"""

import logging
import random
import time

from kohakuefda.layout.depot_via import brick_rotation
from kohakuefda.layout.site import Anchor, Site
from kohakuefda.model.control import CancelledError
from kohakuefda.model.geometry import Edge, rotated_size
from kohakuefda.util.progress import Ticker

log = logging.getLogger(__name__)
# How many times a pass is re-laid with the machines it could not seat put first.
PROMOTIONS = 3
ENTRY_ROTATION = {Edge.W: 0, Edge.N: 90, Edge.E: 180, Edge.S: 270}
ANCHOR_KINDS = ("depot", "zone")
UNGROUPED = "~"


class Spread:
    """Lays every block out with room around it; ``run`` returns whether all of them stand."""

    def __init__(self, site: Site, params: dict, rng: random.Random) -> None:
        self.site = site
        self.params = params
        self.rng = rng
        self.gap = max(0, int(params["spread_gap"]))
        self.widest = max(self.gap, int(params["spread_widest"]))
        self.top_down = str(params["flow_order"]) == "top-down"
        self.tries = max(1, int(params["candidate_tries"]))
        self.grid_squares: list[tuple[int, int]] = []
        self.next_square = 0
        self.laid: list[str] = []
        self.failed: list[str] = []

    # ---- order ----------------------------------------------------------

    def rank(self) -> dict[str, int]:
        """How far each block is along the flow: zero at the machines nothing feeds, one more
        than its deepest producer everywhere else. A whole group takes its earliest member's
        rank so a gas unit or a bus part is down before anything that must touch it."""
        site = self.site
        rank = dict.fromkeys(site.blocks, 0)
        for _ in range(len(rank)):
            changed = False
            for wire in site.wires:
                a, b = site.owner[wire.source].id, site.owner[wire.sink].id
                if a != b and rank[b] <= rank[a]:
                    rank[b] = rank[a] + 1
                    changed = True
            if not changed:
                break
        for members in site.groups.values():
            first = min(rank[b.id] for b in members)
            for block in members:
                rank[block.id] = first
        return rank

    def neighbours(self) -> dict[str, list[str]]:
        """Who each block hands to, or takes from when the order runs against the flow."""
        site = self.site
        out: dict[str, list[str]] = {i: [] for i in site.blocks}
        for wire in site.wires:
            a, b = site.owner[wire.source].id, site.owner[wire.sink].id
            if a == b:
                continue
            first, second = (b, a) if self.top_down else (a, b)
            if second not in out[first]:
                out[first].append(second)
        return out

    def order(self, shuffle: bool = False) -> list[str]:
        """Blocks in the order they are laid: each chain of the flow walked to its end before
        the next one starts, so a machine lands beside the one that feeds it rather than a
        shelf away from it, with each group whole and its anchor first.

        Taking the flow one rank at a time instead puts every machine of a step side by side
        and leaves its consumer wherever the shelf had got to, and the lane between them then
        costs more floor than the machine does.
        """
        site = self.site
        rank = self.rank()
        deepest = max(rank.values(), default=0)
        after = self.neighbours()

        def depth(block_id: str) -> int:
            return deepest - rank[block_id] if self.top_down else rank[block_id]

        def group_of(block_id: str) -> list[str]:
            block = site.blocks[block_id]
            members = (
                [b.id for b in site.groups[block.group]] if block.group else [block_id]
            )
            return sorted(
                members, key=lambda i: (site.blocks[i].kind not in ANCHOR_KINDS, i)
            )

        seen: set[str] = set()
        out: list[str] = []
        jitter = (lambda i: self.rng.random()) if shuffle else (lambda i: 0.0)
        roots = sorted(site.blocks, key=lambda i: (depth(i), jitter(i), i))
        for root in roots:
            if root in seen:
                continue
            stack = [root]
            while stack:
                block_id = stack.pop()
                if block_id in seen:
                    continue
                for member in group_of(block_id):
                    if member not in seen:
                        seen.add(member)
                        out.append(member)
                stack += sorted(
                    (i for i in after[block_id] if i not in seen),
                    key=lambda i: (-depth(i), jitter(i), i),
                )
        return out

    # ---- where a block goes ---------------------------------------------

    def clearance(self, block_id: str, rotation: int, gap: int) -> dict[Edge, int]:
        """Free cells each side of a block needs: one where a wired port sits on that edge,
        because a connection always costs a cell (LOG-11), and none where no port does,
        because machines may share edges (PLC-01). ``gap`` is added to the sides that carry
        a port, for the lanes that pass along them rather than stopping there.

        A machine whose ports are all on two opposite faces therefore packs solid against its
        neighbours on the other two, and only the faces that actually emit or accept anything
        cost floor.
        """
        site = self.site
        block = site.blocks[block_id]
        wired = {
            key
            for wire in site.touching[block_id]
            for key in (wire.source, wire.sink)
            if key in block.pins
        }
        out = dict.fromkeys((Edge.N, Edge.E, Edge.S, Edge.W), 0)
        for key, _, edge in block.ports_at(rotation):
            if key in wired:
                out[edge] = 1 + gap
        return out

    def envelope(
        self, block_id: str, rotation: int, gap: int
    ) -> tuple[int, int, int, int]:
        """The room a block takes with its clearance: cells left and above the anchor, then
        the width and height of the whole envelope."""
        block = self.site.blocks[block_id]
        pad = self.clearance(block_id, rotation, gap)
        width, height = rotated_size(block.width, block.height, rotation)
        return (
            pad[Edge.W],
            pad[Edge.N],
            pad[Edge.W] + width + pad[Edge.E],
            pad[Edge.N] + height + pad[Edge.S],
        )

    def beside(self, block_id: str, gap: int) -> bool:
        """Put the block against a partner already standing, closest first.

        A lane costs floor like a machine does (LOG-11), so the position that leaves a block
        one cell from what feeds it costs a cell, and the shelf position that leaves it two
        rows away costs the whole path. Only when no partner stands, or every position
        against them is taken, is the shelf worth walking.
        """
        site = self.site
        anchors = site.facing_anchors(block_id, 1 + gap)
        if not anchors:
            return False
        partners = [
            (other.x, other.y)
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
        if not partners:
            return False

        def near(anchor: Anchor) -> int:
            return min(abs(anchor[0] - px) + abs(anchor[1] - py) for px, py in partners)

        block = site.blocks[block_id]
        room = [a for a in set(anchors) if self.envelope_free(block_id, a, gap)]
        for anchor in sorted(room, key=near)[: self.tries]:
            if site.free_for(block, block.cells_at(*anchor)) and site.place(
                block_id, *anchor
            ):
                return True
        return False

    def envelope_free(self, block_id: str, anchor: Anchor, gap: int) -> bool:
        """Whether a block's clearance is free as well as its footprint.

        Standing a machine flush against its partner is the shortest lane but it seals the
        faces the next machine needs, so the position only counts when the cells its own
        ports must leave by are free too.
        """
        site = self.site
        block = site.blocks[block_id]
        x, y, rotation = anchor
        left, top, width, height = self.envelope(block_id, rotation, gap)
        own = set(block.cells_at(x, y, rotation))
        cells = [
            (x - left + dx, y - top + dy)
            for dy in range(height)
            for dx in range(width)
            if (x - left + dx, y - top + dy) not in own
        ]
        return site.grid.free_for(cells, site.area, site.cells_of.get(block_id, []))

    def pitch(self, gap: int) -> int:
        """The lattice step: the widest free block, the cell its lanes leave by, and ``gap``.

        One cell is the floor, because a connection always costs one (LOG-11). The pylon does
        not need room beside its machine: partial coverage powers a machine and a single
        shared cell is enough (COV-02), so a pylon reaches from any corridor whose square
        overlaps it. ``gap`` widens the corridor for the attempts that need more.
        """
        site = self.site
        free = [
            b
            for b in site.blocks.values()
            if b.constraint not in ("slot", "edge") and not b.group
        ]
        widest = max((max(b.width, b.height) for b in free), default=1)
        return widest + 1 + gap

    def squares(self, gap: int) -> list[tuple[int, int]]:
        """Lattice squares in a serpentine, so a block lands next to the one before it and
        the walk turns back on itself at the end of a row instead of jumping home."""
        x0, y0, x1, y1 = self.site.area
        step = self.pitch(gap)
        columns = max(1, (x1 - x0) // step)
        rows = max(1, (y1 - y0) // step)
        out: list[tuple[int, int]] = []
        for j in range(rows):
            span = range(columns) if j % 2 == 0 else reversed(range(columns))
            out += [(x0 + i * step, y0 + j * step) for i in span]
        return out

    def settle(self, block_id: str, gap: int) -> bool:
        """Stand the block in the next lattice square that will take it.

        Each position is offered to ``place``, which routes what the block touches and
        refuses outright when a lane has no path, so a block only ever stands where it is
        actually wired.
        """
        site = self.site
        start = self.next_square
        for step in range(len(self.grid_squares)):
            index = (start + step) % len(self.grid_squares)
            x, y = self.grid_squares[index]
            for rotation in self.turns(block_id):
                if site.place(block_id, x, y, rotation):
                    self.next_square = index + 1
                    return True
        return False

    def anchors_for(self, block_id: str) -> list[Anchor] | None:
        """The positions a constrained block is allowed, or ``None`` when it is free to take
        the next place on the shelf."""
        site = self.site
        block = site.blocks[block_id]
        if block.constraint == "slot":
            machine = site.dataset.machines[block.fragment.machine_id]
            return [
                (slot.x, slot.y, brick_rotation(machine, slot.side))
                for slot in site.board.slots
            ]
        if block.constraint == "edge":
            return self.border_anchors(block_id)
        if block.group and any(
            b.id in site.placed for b in site.groups[block.group] if b.id != block_id
        ):
            return site.group_anchors(block_id)
        return None

    def border_anchors(self, block_id: str) -> list[Anchor]:
        """Border cells of the area, nearest first to the machine this outside input feeds."""
        site = self.site
        x0, y0, x1, y1 = site.area
        sides = {Edge(letter) for letter in str(self.params["entry_sides"])}
        cells: list[tuple[tuple[int, int], Edge]] = []
        if Edge.N in sides:
            cells += [((x, y0), Edge.N) for x in range(x0, x1)]
        if Edge.S in sides:
            cells += [((x, y1 - 1), Edge.S) for x in range(x0, x1)]
        if Edge.W in sides:
            cells += [((x0, y), Edge.W) for y in range(y0, y1)]
        if Edge.E in sides:
            cells += [((x1 - 1, y), Edge.E) for y in range(y0, y1)]
        target = self._target_cell(block_id)
        cells.sort(
            key=lambda item: abs(item[0][0] - target[0]) + abs(item[0][1] - target[1])
        )
        return [(cell[0], cell[1], ENTRY_ROTATION[side]) for cell, side in cells]

    def _target_cell(self, block_id: str) -> tuple[int, int]:
        site = self.site
        for wire in site.touching[block_id]:
            other = site.owner[wire.sink]
            if other.id != block_id and other.id in site.placed:
                return (other.x, other.y)
        return (site.area[0], site.area[1])

    def turns(self, block_id: str) -> list[int]:
        """Rotations to try, the one whose ports point at the partners already standing
        first, so the lane between them is the short way round rather than the long way.
        """
        site = self.site
        partners = [
            (other.x, other.y)
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
        if not partners or self.next_square >= len(self.grid_squares):
            return [0, 90, 180, 270]
        block = site.blocks[block_id]
        x, y = self.grid_squares[self.next_square]
        px = sum(p[0] for p in partners) / len(partners)
        py = sum(p[1] for p in partners) / len(partners)

        def reach(rotation: int) -> float:
            return min(
                (
                    abs(x + cell[0] - px) + abs(y + cell[1] - py)
                    for _, cell, _ in block.ports_at(rotation)
                ),
                default=0.0,
            )

        return sorted((0, 90, 180, 270), key=reach)

    # ---- the pass -------------------------------------------------------

    def lay(self, order: list[str], gap: int) -> list[str]:
        """One lattice: every block of ``order`` in a square of its own, placed and wired.
        Returns the blocks that found nowhere."""
        site = self.site
        for block_id in list(site.placed):
            site.remove(block_id)
        self.grid_squares = self.squares(gap)
        self.next_square = 0
        missed: list[str] = []
        self.laid = list(order)
        for block_id in self.laid:
            if not self.stand(block_id, gap):
                missed.append(block_id)
        for block_id in list(missed):
            if self.stand(block_id, gap):
                missed.remove(block_id)
        return missed

    def rebuild(
        self, anchors: dict[str, Anchor], order: list[str], observe=None
    ) -> bool:
        """Stand every block again where another search put it, then route the whole layout.

        The order comes with the anchors because routing depends on it: a lane laid before
        the machine that would have shared its cells takes a different path, so replaying the
        same positions in a different order does not give back the same layout.
        """
        site = self.site
        for block_id in list(site.placed):
            site.remove(block_id)
        for block_id in order:
            anchor = anchors.get(block_id)
            if anchor is not None and not site.place(block_id, *anchor):
                return False
            if observe is not None:
                observe(self.frame("build"))
        return not site.unrouted()

    def stand(self, block_id: str, gap: int) -> bool:
        """Put one block where it is allowed: on its bus slot or the border when it is pinned
        there, against its group when one is already standing, else in a lattice square.
        """
        site = self.site
        anchors = self.anchors_for(block_id)
        if anchors is not None:
            return any(site.place(block_id, *a) for a in anchors)
        return self.settle(block_id, gap)

    def gaps(self) -> range:
        return range(self.gap, self.widest + 1)

    def frame(self, kind: str) -> dict:
        """The layout as it stands, for a watcher to draw."""
        site = self.site
        x0, y0, x1, y1 = site.bbox()
        return {
            "kind": kind,
            "blocks": [
                [i, b.x, b.y, b.rotation]
                for i, b in site.blocks.items()
                if i in site.placed
            ],
            "wires": [[w.id, w.kind, w.net_id, w.cells] for w in site.wires if w.cells],
            "rect": [x0, y0, x1, y1],
            "cost": site.cost(),
            "pylons": [],
            "entries": [],
            "placed": len(site.placed),
            "total": len(site.blocks),
            "failed": [w.id for w in site.unrouted()],
            "clean": not site.unplaced(),
        }

    def standing(self, whole: bool) -> tuple[int, int, int, int, int, int]:
        """How good a pass came out: legal first, then how small.

        The gaps and the two directions of the flow are a handful of arrangements, not a
        search, and stopping at the first one that comes out whole leaves the smaller ones on
        the table for nothing. Legal means every rule the site can answer for, not just that
        the machines stand and the lanes run: a tighter pass that leaves a machine off the
        power or a brick off its bus face is not the better one.
        """
        site = self.site
        x0, y0, x1, y1 = site.bbox()
        return (
            0 if whole else 1,
            len(self.failed),
            len(site.unrouted()),
            len(site.pylons()[1]),
            site.faults(),
            (x1 - x0) * (y1 - y0),
        )

    def pass_at(
        self, gap: int, observe=None, cancelled=None, promote: list[str] | None = None
    ) -> bool:
        """Lay every machine once with this much room round each square.

        One machine is one step: it stands, its lanes are routed where it stands, a watcher is
        told and the cancel is answered, so nothing here takes longer than placing a machine.
        """
        site = self.site
        for block_id in list(site.placed):
            site.remove(block_id)
        self.grid_squares = self.squares(gap)
        self.next_square = 0
        self.laid = self.order()
        if promote:
            ahead = [b for b in promote if b in self.laid]
            self.laid = ahead + [b for b in self.laid if b not in set(ahead)]
        self.failed = []
        ticker = Ticker(len(self.laid), f"spread gap {gap}")
        for index, block_id in enumerate(self.laid):
            if cancelled is not None and cancelled():
                raise CancelledError("layout cancelled")
            if not self.stand(block_id, gap):
                self.failed.append(block_id)
            if observe is not None:
                observe(self.frame("build"))
            ticker.tick(index + 1, block_id, len(self.failed))
        for block_id in list(self.failed):
            if self.stand(block_id, gap):
                self.failed.remove(block_id)
                if observe is not None:
                    observe(self.frame("build"))
        if self.failed:
            self.seat(gap, observe)
        ticker.done()
        return not self.failed and not site.unrouted()

    def seat(self, gap: int, observe=None) -> None:
        """Put the machines that found nowhere down anyway, and route the netlist as a whole.

        A machine is refused for want of a path far more often than for want of room: the lanes
        already laid have taken the corridors out of every square by the time it is offered
        one. Standing it without routing and handing the whole netlist to the router lets it
        rip up what is in the way and negotiate, which is the one thing placing a lane at a
        time cannot do.
        """
        site = self.site
        state = site.snapshot()
        homeless = list(self.failed)
        for block_id in homeless:
            for x, y in self.grid_squares:
                if any(
                    site.place(block_id, x, y, rotation, route=False)
                    for rotation in self.turns(block_id)
                ):
                    self.failed.remove(block_id)
                    break
        if site.unplaced():
            site.restore(state)
            self.failed = homeless
            return
        site.router.route(strict=False)
        if site.unrouted():
            site.restore(state)
            self.failed = homeless
            return
        if observe is not None:
            observe(self.frame("build"))

    def run(self, observe=None, cancelled=None) -> bool:
        """Lay the spread once, along the flow, wiring each machine as it stands.

        There is nothing here worth searching. A square holds the widest block with a lane's
        room beside it, so a machine that stands has room for what it is wired to, and walking
        the flow puts it beside the machine that feeds it; routing it the moment it stands is
        easy precisely because the room around it is still empty. Laying the same lattice tens
        of thousands of times over shuffled orders bought a few per cent of area for a hundred
        times the work, and the placement walk that follows buys that properly.

        One machine is one step: it stands, its lanes are routed, a watcher is told, and the
        cancel is answered. Nothing here takes longer than placing a single machine.
        """
        site = self.site
        started = time.monotonic()
        kept: tuple | None = None
        wanted = self.top_down
        for gap in self.gaps():
            for top_down in (wanted, not wanted):
                self.top_down = top_down
                promote: list[str] = []
                for _ in range(PROMOTIONS):
                    whole = self.pass_at(gap, observe, cancelled, promote)
                    score = self.standing(whole)
                    if kept is None or score < kept[0]:
                        kept = (
                            score,
                            site.snapshot(),
                            list(self.failed),
                            list(self.laid),
                        )
                    if whole or not self.failed or set(self.failed) <= set(promote):
                        break
                    promote = list(self.failed) + promote
                    log.debug("seating the homeless first", gap=gap, blocks=promote)
                if whole:
                    break
            if whole:
                break
        site.restore(kept[1])
        self.failed = list(kept[2])
        self.laid = list(kept[3])
        whole = not self.failed and not site.unrouted()
        x0, y0, x1, y1 = site.bbox()
        log.info(
            "spread done" if whole else "spread incomplete",
            seconds=round(time.monotonic() - started, 2),
            placed=f"{len(site.placed)}/{len(site.blocks)}",
            size=f"{x1 - x0}x{y1 - y0}",
            wires=site.wire_cells(),
            homeless=len(self.failed),
            unrouted=len(site.unrouted()),
        )
        return whole
