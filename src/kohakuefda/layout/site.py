"""The live layout: machines at absolute cells and every wire routed on one grid.

There is no packing pass and no routing pass. A machine enters the layout only through
``place``, which rips the wires its footprint would cover, puts the machine down, routes every
wire whose two ends are now placed, and undoes all of it when any of them has no path. A
placement that cannot be wired therefore never exists, and what a placement costs is what the
layout costs with its wires in it (game-knowledge LOG-11: a connection always costs at least one
belt or pipe cell, so a wire is floor area like a machine is).

**Illegal is not priced.** An overlap, a lane with no port to leave by, a shared cell that is not
a legal crossing, a machine outside its gas zone, a brick off its bus, a machine no pylon can
reach, a machine with nowhere to stand at all: each makes ``place`` fail outright, and any that
survives costs ``ILLEGAL`` (2**31-1) apiece — beyond every real term put together, yet finite, so
two broken layouts still compare and the search can climb out of one.
"""

import logging
from collections import Counter
from collections.abc import Iterator

from kohakuefda.layout.assemble import world_pins
from kohakuefda.layout.board import Board
from kohakuefda.layout.coverage import zone_rect
from kohakuefda.layout.depot_via import brick_rotation
from kohakuefda.layout.groups import faults
from kohakuefda.layout.place import Block, PinKey
from kohakuefda.model.cells import BUS_GROUP, Netlist
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.geometry import (
    ROTATIONS,
    Edge,
    Rotation,
    edge_step,
    rotated_size,
)
from kohakuefda.model.layout import Cell, Rect
from kohakuefda.model.machines import GROUND, SKY
from kohakuefda.model.sinks import ZONE_SIDE
from kohakuefda.route.pathfinder import RouteGrid
from kohakuefda.route.router import (
    LAYER,
    ROLE_ORDER,
    Router,
    Wire,
    ring_cells,
    wires_of,
)

log = logging.getLogger(__name__)
OPPOSITE = {Edge.N: Edge.S, Edge.S: Edge.N, Edge.E: Edge.W, Edge.W: Edge.E}
ROUTE_ROUNDS = 4
ORIGIN_WINDOW = 3
ILLEGAL = float(2**31 - 1)
Anchor = tuple[int, int, Rotation]
Snapshot = tuple


class Site:
    """Every block, the grid they stand on, and the router that holds their wires."""

    def __init__(
        self,
        dataset: Dataset,
        netlist: Netlist,
        board: Board,
        params: dict,
    ) -> None:
        self.dataset = dataset
        self.netlist = netlist
        self.board = board
        self.params = params
        self.pylon = dataset.pylons[str(params["pylon"])]
        self.present = float(params["present_cost"])
        self.width, self.height = board.grid
        self.area: Rect = board.area
        self.blocks = {c.id: Block.of_cell(c, dataset) for c in netlist.cells}
        self.wires: list[Wire] = wires_of(netlist)
        self.owner: dict[PinKey, Block] = {
            key: block for block in self.blocks.values() for key in block.pins
        }
        self.touching: dict[str, list[Wire]] = {i: [] for i in self.blocks}
        for wire in self.wires:
            self.touching[self.owner[wire.source].id].append(wire)
            other = self.owner[wire.sink].id
            if other != self.owner[wire.source].id:
                self.touching[other].append(wire)
        self.groups: dict[str, list[Block]] = {}
        for block in self.blocks.values():
            if block.group:
                self.groups.setdefault(block.group, []).append(block)
        blocked: list[set[Cell]] = [set(), set()]
        blocked[GROUND] |= ring_cells(self.width, self.height, self.area)
        blocked[GROUND] |= set(board.fixed)
        blocked[SKY] |= set(board.fixed)
        self.grid = RouteGrid(
            self.width,
            self.height,
            blocked,
            float(params["turn_cost"]),
            float(params["bridge_cost"]),
            float(params["history_cost"]),
        )
        self.router = Router(
            dataset,
            self.grid,
            {},
            self.wires,
            self.present,
            float(params["present_growth"]),
            int(params["route_iterations"]),
        )
        self.router.share = False
        self.router.unit_area = self.area
        self.placed: dict[str, Anchor] = {}
        self.cells_of: dict[str, list[Cell]] = {}
        self.refused: Counter[str] = Counter()

    # ---- geometry -------------------------------------------------------

    def free_for(self, block: Block, cells: list[Cell]) -> bool:
        """Whether a footprint fits: inside the area, clear of every other machine, and far
        enough from the border to seat the group that attaches to it — a Depot Bus part put
        flush in a corner loses the sides its bricks would take (DEP-06)."""
        room = self._group_room(block)
        x0, y0, x1, y1 = self.area
        area = (x0 + room, y0 + room, x1 - room, y1 - room)
        return self.grid.free_for(cells, area, self.cells_of.get(block.id, []))

    def ready(self, wire: Wire) -> bool:
        return (
            self.owner[wire.source].id in self.placed
            and self.owner[wire.sink].id in self.placed
        )

    # ---- the primitive --------------------------------------------------

    def place(
        self, block_id: str, x: int, y: int, rotation: Rotation, route: bool = True
    ) -> bool:
        """Put a machine down and wire it. ``False`` and no change when the result would be
        anything the game refuses; ``refused`` counts why, for the log.

        ``wire`` off puts the machine down without routing what it touches, for a caller that
        lays every machine out before it routes anything; the geometry, the group rules and
        the power are still checked, and the lanes are left for ``wire_up``.
        """
        block = self.blocks[block_id]
        cells = block.cells_at(x, y, rotation)
        if not self.free_for(block, cells):
            self.refused["no room"] += 1
            return False
        state = self.snapshot()
        self.router.forced = set()
        covered = [
            w for w in self.wires if w.cells and not set(w.cells).isdisjoint(cells)
        ]
        required = {w.id for w in self.touching[block_id]}
        for wire in covered:
            required.update(w.id for w in self.router.rip(wire))
        self._occupy(block, cells, x, y, rotation)
        reason = self._refusal(block, set(cells), required, route)
        if reason is None:
            return True
        self.refused[reason] += 1
        self.restore(state)
        return False

    def _refusal(
        self, block: Block, cells: set[Cell], required: set[str], route: bool = True
    ) -> str | None:
        """Why this placement cannot stand, or ``None`` when it may."""
        if self.closes_a_port(block, cells):
            return "port shut"
        if route and not self.wire_up(required):
            return "no path"
        if self.faults():
            return "group rule"
        if self.pylons()[1]:
            return "no pylon"
        return None

    def closes_a_port(self, block: Block, cells: set[Cell]) -> bool:
        """Whether this placement left a wired pin with no port a lane could leave by: one of
        the block's own, facing the ring or a machine, or another machine's that the footprint
        now stands in front of. Such a lane is unroutable however the rest is arranged, so no
        placement may do it. A pin that was already shut elsewhere is not this one's doing.
        """
        for wire in self.wires:
            for key in (wire.source, wire.sink):
                pin = self.router.pins.get(key)
                if pin is None:
                    continue
                if key not in block.pins and not any(
                    o.outside in cells for o in pin.options
                ):
                    continue
                layer = LAYER[pin.kind]
                if (
                    self.grid.first_open(layer, [o.outside for o in pin.options])
                    is None
                ):
                    return True
        return False

    def wire_up(self, required: set[str], strict: bool = True) -> bool:
        """Route the wires this placement disturbed — the block's own and any it ripped — and
        fail if one of them has no path. Wires elsewhere that are still without one are left
        for a move of their own machine; the cost counts them meanwhile, so the search is not
        free to ignore them.

        ``strict`` off routes the rest of the set after one has failed, for a caller that
        wants every lane it can get and a list of the ones it did not.
        """
        for _ in range(ROUTE_ROUNDS):
            self.router.ripped_now = []
            todo = [
                w
                for w in self.wires
                if w.id in required and self.ready(w) and not w.routed
            ]
            if not todo:
                return True
            for wire in self._ordered(todo):
                routed = wire.routed or self.router._route_wire(wire, self.present)
                if not routed and strict:
                    return False
            required.update(w.id for w in self.router.ripped_now)
        return not [
            w for w in self.wires if w.id in required and self.ready(w) and not w.routed
        ]

    def remove(self, block_id: str) -> None:
        """Take a machine out with the wires that touch it."""
        block = self.blocks[block_id]
        for wire in self.touching[block_id]:
            if wire.cells or wire.branch is not None or wire.join is not None:
                self.router.rip(wire)
            for key in (wire.source, wire.sink):
                if key in block.pins:
                    self.router.unreserve_pin(key, wire)
        for cell in self.cells_of.pop(block_id, ()):
            self.grid.unblock(GROUND, cell)
            self.grid.unblock(SKY, cell)
        self.placed.pop(block_id, None)
        for key in block.pins:
            self.router.pins.pop(key, None)

    def _occupy(
        self, block: Block, cells: list[Cell], x: int, y: int, rotation: Rotation
    ) -> None:
        block.x, block.y, block.rotation = x, y, rotation
        self.cells_of[block.id] = cells
        for cell in cells:
            self.grid.block(GROUND, cell, owned=True)
            self.grid.block(SKY, cell, owned=True)
        self.router.pins.update(world_pins([block]))
        self.placed[block.id] = (x, y, rotation)
        for wire in self.touching[block.id]:
            for key in (wire.source, wire.sink):
                if key in block.pins:
                    self.router.reserve_pin(key, wire)

    def _ordered(self, wires: list[Wire]) -> list[Wire]:
        """The router's own order: pipes first, then a tree's trunk before the joins that
        feed it and the branches that leave it, since a join has nothing to reach until its
        trunk is down."""

        def span(wire: Wire) -> int:
            a = self.router.pins[wire.source].outside
            b = self.router.pins[wire.sink].outside
            return abs(a[0] - b[0]) + abs(a[1] - b[1])

        return sorted(
            wires,
            key=lambda w: (
                w.kind != "pipe",
                ROLE_ORDER[w.role],
                -w.rate,
                -span(w),
                w.id,
            ),
        )

    # ---- undo -----------------------------------------------------------

    def snapshot(self) -> Snapshot:
        return (
            dict(self.placed),
            {k: list(v) for k, v in self.cells_of.items()},
            {i: (b.x, b.y, b.rotation) for i, b in self.blocks.items()},
            self.grid.python_state(),
            {k: set(v) for k, v in self.router.taken.items()},
            {k: list(v) for k, v in self.router.trees.items()},
            {
                w.id: (list(w.cells), w.branch, w.join, w.source_port, w.sink_port)
                for w in self.wires
            },
            dict(self.router.pins),
            self.grid.save(),
        )

    def restore(self, state: Snapshot) -> None:
        self.placed = dict(state[0])
        self.cells_of = {k: list(v) for k, v in state[1].items()}
        for block_id, (x, y, rotation) in state[2].items():
            block = self.blocks[block_id]
            block.x, block.y, block.rotation = x, y, rotation
        self.grid.restore_python(state[3])
        self.grid.load(state[8])
        self.router.taken = {k: set(v) for k, v in state[4].items()}
        self.router.trees = {k: list(v) for k, v in state[5].items()}
        self.router.pins = dict(state[7])
        for wire in self.wires:
            cells, branch, join, source_port, sink_port = state[6][wire.id]
            wire.cells = list(cells)
            wire.branch = branch
            wire.join = join
            wire.source_port = source_port
            wire.sink_port = sink_port

    # ---- measurement ----------------------------------------------------

    def occupied(self) -> set[Cell]:
        """Every cell the line uses: machines, belts, pipes and their junctions."""
        native = self.grid.used()
        if native is not None:
            return native
        cells: set[Cell] = set()
        for owned in self.cells_of.values():
            cells.update(owned)
        for wire in self.wires:
            cells.update(wire.cells)
            for junction in (wire.branch, wire.join):
                if junction is not None:
                    cells.add(junction)
        return cells

    def bbox(self) -> Rect:
        if self.grid.native is not None:
            extent = self.grid.extent()
            return self.area if extent is None else tuple(extent)
        cells = self.occupied()
        if not cells:
            return self.area
        xs = [c[0] for c in cells]
        ys = [c[1] for c in cells]
        return (min(xs), min(ys), max(xs) + 1, max(ys) + 1)

    def junctions(self) -> int:
        return sum(
            1
            for wire in self.wires
            for junction in (wire.branch, wire.join)
            if junction is not None
        )

    def wire_cells(self) -> int:
        return sum(len(w.cells) for w in self.wires)

    def faults(self) -> int:
        """Group rules broken by the blocks placement is free to move. A brick on a fixed
        Depot Bus slot sits where the game put the bus, so it is never at fault."""
        placed = {
            name: [b for b in members if b.id in self.placed and b.constraint != "slot"]
            for name, members in self.groups.items()
        }
        return faults({k: v for k, v in placed.items() if v})

    def pylons(self, used: set[Cell] | None = None) -> tuple[list[Cell], list[str]]:
        """Where the pylons go and which machines none of them reaches; the same sweep the
        cost is measured with, so what is paid for is what gets built."""
        if used is None:
            used = set() if self.grid.native is not None else self.occupied()
        size = self.dataset.machines[self.pylon.machine_id].width
        windows, uncovered = self.power(used)
        anchors: list[Cell] = []
        taken: list[Cell] = []
        for window, members in windows:
            spot = self._pylon_spot(window, used, size, taken)
            if spot is None:
                uncovered += members
                continue
            anchors.append(spot)
            footprint = {
                (spot[0] + dx, spot[1] + dy) for dy in range(size) for dx in range(size)
            }
            taken += sorted(footprint)
            used |= footprint
        return anchors, uncovered

    def anchor_window(self, rect: Rect, size: int, reach: int) -> Rect:
        """Where a pylon may stand to power ``rect``.

        A machine is powered when its footprint *touches* a pylon's square, not when the
        square swallows it whole (game-knowledge COV-02), so the anchors that serve a machine
        are every one whose square overlaps it. Clipped to the area, since that is where a
        pylon may stand.
        """
        x0, y0, x1, y1 = rect
        area = self.area
        return (
            max(area[0], x0 - size - reach + 1),
            max(area[1], y0 - size - reach + 1),
            min(area[2] - size + 1, x1 + reach),
            min(area[3] - size + 1, y1 + reach),
        )

    def power(
        self, used: set[Cell] | None = None
    ) -> tuple[list[tuple[Rect, list[str]]], list[str]]:
        """The machines one pylon each can serve, as the window that pylon may stand in, and
        the machines no pylon can reach at all.

        Every machine has a window of anchors that would power it; a set of machines shares a
        pylon exactly when their windows have a cell in common that is free for the pylon to
        stand on. Machines are swept into the first such group, so what is counted is what
        gets built.
        """
        used = self.occupied() if used is None else used
        machine = self.dataset.machines[self.pylon.machine_id]
        size, reach = machine.width, self.pylon.reach
        rects = sorted(
            (
                (block_id, rect)
                for block_id in self.placed
                if self.blocks[block_id].powered
                for rect in self.blocks[block_id].machine_rects()
            ),
            key=lambda item: (item[1][1], item[1][0]),
        )
        groups: list[tuple[Rect, list[str]]] = []
        uncovered: list[str] = []
        for block_id, rect in rects:
            window = self.anchor_window(rect, size, reach)
            for index, (shared, members) in enumerate(groups):
                merged = (
                    max(shared[0], window[0]),
                    max(shared[1], window[1]),
                    min(shared[2], window[2]),
                    min(shared[3], window[3]),
                )
                if (
                    merged[0] < merged[2]
                    and merged[1] < merged[3]
                    and self._pylon_spot(merged, used, size) is not None
                ):
                    groups[index] = (merged, members + [block_id])
                    break
            else:
                if self._pylon_spot(window, used, size) is not None:
                    groups.append((window, [block_id]))
                elif block_id not in uncovered:
                    uncovered.append(block_id)
        return groups, uncovered

    def _pylon_spot(
        self,
        window: Rect,
        used: set[Cell],
        size: int,
        taken: list[Cell] | None = None,
    ) -> Cell | None:
        """A free square inside ``window`` that a pylon can stand on, or ``None``."""
        if window[0] >= window[2] or window[1] >= window[3]:
            return None
        if self.grid.native is not None:
            spot = self.grid.free_square(window, size, taken or [])
            return None if spot is None else tuple(spot)
        blocked = set(taken or ()) | used
        for py in range(window[1], window[3]):
            for px in range(window[0], window[2]):
                if all(
                    (px + dx, py + dy) not in blocked
                    for dy in range(size)
                    for dx in range(size)
                ):
                    return (px, py)
        return None

    def violations(self, used: set[Cell] | None = None) -> int:
        """Everything the game would refuse about the layout as it stands: a group rule broken,
        a machine no pylon can reach, a lane between two placed machines with no path.
        """
        return self.faults() + len(self.pylons(used)[1]) + len(self.unrouted())

    def cost(self) -> float:
        """``ILLEGAL`` per rule the layout breaks, then the rectangle it needs and how far from
        square it is, what its wires, junctions and pylons cost, a pull to the area's corner so
        two layouts that differ only by a translation differ in cost, and what the machines it
        has not placed yet are worth.

        The shape term matters because the basement is a square: a line of the same area that
        runs long and thin stops fitting long before a compact one does, and whatever reaches
        past the square's side does not fit at all.
        """
        x0, y0, x1, y1 = self.bbox()
        pull = (x0 - self.area[0]) + (y0 - self.area[1])
        clusters, uncovered = self.power()
        width, height = x1 - x0, y1 - y0
        over = max(0, width - self.board.square[0]) * height
        over += max(0, height - self.board.square[1]) * width
        return ILLEGAL * self.broken(uncovered) + (
            width * height
            + float(self.params["w_shape"]) * abs(width - height)
            + float(self.params["w_over"]) * over
            + float(self.params["w_wire"]) * self.wire_cells()
            + float(self.params["w_unit"]) * self.junctions()
            + float(self.params["w_pull"]) * pull
            + float(self.params["w_pylon"]) * len(clusters)
        )

    def broken(self, uncovered: list[str] | None = None) -> int:
        """How many rules the layout breaks: a group fault, a machine no pylon can reach, a
        lane with no path, a machine with nowhere to stand."""
        if uncovered is None:
            uncovered = self.pylons()[1]
        return (
            self.faults() + len(uncovered) + len(self.unrouted()) + len(self.unplaced())
        )

    def plain(self) -> float:
        """What the layout costs with the broken rules left out: the number the annealing
        schedule is scaled by, since the illegal term would otherwise set the temperature.
        """
        return self.cost() - ILLEGAL * self.broken()

    def legal(self) -> bool:
        return not self.violations()

    def unplaced(self) -> list[str]:
        return [i for i in self.blocks if i not in self.placed]

    def unrouted(self) -> list[Wire]:
        return [w for w in self.wires if self.ready(w) and not w.routed]

    # ---- candidate positions -------------------------------------------

    def facing_anchors(self, block_id: str, radius: int) -> list[Anchor]:
        """Anchors that bring one of the block's ports within ``radius`` cells of the port of a
        placed partner it exchanges something with: every short connection the pair could make,
        straight or around a corner, the single shared cell included. Routing decides which of
        them is real, so nothing here assumes the lane runs in a straight line."""
        block = self.blocks[block_id]
        offsets = [
            (ox, oy)
            for oy in range(-radius, radius + 1)
            for ox in range(-radius, radius + 1)
            if abs(ox) + abs(oy) <= radius
        ]
        out: set[Anchor] = set()
        for wire in self.touching[block_id]:
            mine, theirs = (
                (wire.source, wire.sink)
                if self.owner[wire.source].id == block_id
                else (wire.sink, wire.source)
            )
            partner = self.router.pins.get(theirs)
            if partner is None or mine not in block.pins:
                continue
            for option in partner.options:
                bx, by = option.outside
                for rotation in ROTATIONS:
                    for key, cell, edge in block.ports_at(rotation):
                        if key != mine:
                            continue
                        dx, dy = edge_step(edge)
                        lx, ly = cell[0] + dx, cell[1] + dy
                        out.update(
                            (bx + ox - lx, by + oy - ly, rotation) for ox, oy in offsets
                        )
        return list(out)

    def every_anchor(self) -> Iterator[Anchor]:
        """Anchors over the whole area, nearest the placed line first: the last resort when no
        position drawn from a partner, a group or the frontier could be placed and wired.

        They come out in rings around the middle of the line, so a caller that wants only the
        first few never pays for the rest of the area.
        """
        x0, y0, x1, y1 = self.area
        bx0, by0, bx1, by1 = self.bbox()
        cx, cy = (bx0 + bx1) // 2, (by0 + by1) // 2
        for radius in range(max(cx - x0, x1 - cx, cy - y0, y1 - cy) + 1):
            for dx in range(-radius, radius + 1):
                rest = radius - abs(dx)
                for dy in {rest, -rest}:
                    x, y = cx + dx, cy + dy
                    if x0 <= x < x1 and y0 <= y < y1:
                        for rotation in ROTATIONS:
                            yield (x, y, rotation)

    def _origin_anchors(self, block: Block) -> list[Anchor]:
        """The area's corner and the cells just inside it, nearest first: where the first
        machine goes. A machine flush in the corner faces the ring with the ports on those
        sides, so the lane it needs comes from standing a cell or two in — and a machine its
        group has to surround, a Depot Bus part or a Gas Dispersing Unit, needs room on the
        corner sides for the members that seat there."""
        x0, y0 = self.area[0], self.area[1]
        window = ORIGIN_WINDOW + self._group_room(block)
        return sorted(
            (
                (x0 + dx, y0 + dy, rotation)
                for dx in range(window)
                for dy in range(window)
                for rotation in ROTATIONS
            ),
            key=lambda a: (a[0] - x0) + (a[1] - y0),
        )

    def _group_room(self, block: Block) -> int:
        """Cells a block's group mates need beside it, when they seat against it."""
        if block.kind != "depot" or not block.group:
            return 0
        return max(
            (
                max(other.width, other.height)
                for other in self.groups[block.group]
                if other.id != block.id
            ),
            default=0,
        )

    def group_anchors(self, block_id: str) -> list[Anchor]:
        """Anchors that satisfy the group rule this block is under: touching the cluster for a
        Depot Bus part or brick, inside the zone for a machine a Gas Dispersing Unit serves,
        and around them for the unit itself."""
        block = self.blocks[block_id]
        if not block.group:
            return []
        members = [
            b
            for b in self.groups[block.group]
            if b.id in self.placed and b.id != block_id
        ]
        if not members:
            return []
        if block.group == BUS_GROUP:
            return self._bus_anchors(block, members)
        if block.kind == "zone":
            return self._holding_anchors(block, members)
        unit = next((b for b in members if b.kind == "zone"), None)
        if unit is None:
            return []
        return self._inside_anchors(block, zone_rect((unit.x, unit.y), unit.width))

    def _bus_anchors(self, block: Block, members: list[Block]) -> list[Anchor]:
        """Where a Depot Bus block may go: a part anywhere against the cluster, a brick along
        a part with its back face on it, which is the only way a brick reaches the bus
        (game-knowledge DEP-06, DEP-09)."""
        parts = [b for b in members if b.kind == "depot"]
        if block.kind == "depot" or not parts:
            return [a for m in members for a in self._touching_anchors(block, m.rect())]
        machine = self.dataset.machines[block.fragment.machine_id]
        out: list[Anchor] = []
        for part in parts:
            px0, py0, px1, py1 = part.rect()
            for side in (Edge.N, Edge.E, Edge.S, Edge.W):
                rotation = brick_rotation(machine, side)
                w, h = rotated_size(block.width, block.height, rotation)
                if side is Edge.S:
                    out += [(x, py0 - h, rotation) for x in range(px0 - w + 1, px1)]
                elif side is Edge.N:
                    out += [(x, py1, rotation) for x in range(px0 - w + 1, px1)]
                elif side is Edge.E:
                    out += [(px0 - w, y, rotation) for y in range(py0 - h + 1, py1)]
                else:
                    out += [(px1, y, rotation) for y in range(py0 - h + 1, py1)]
        return out

    def _touching_anchors(self, block: Block, rect: Rect) -> list[Anchor]:
        """Anchors where the block shares an edge with ``rect``."""
        x0, y0, x1, y1 = rect
        out: list[Anchor] = []
        for rotation in ROTATIONS:
            w, h = rotated_size(block.width, block.height, rotation)
            for x in range(x0 - w + 1, x1):
                out.append((x, y0 - h, rotation))
                out.append((x, y1, rotation))
            for y in range(y0 - h + 1, y1):
                out.append((x0 - w, y, rotation))
                out.append((x1, y, rotation))
        return out

    def _inside_anchors(self, block: Block, zone: Rect) -> list[Anchor]:
        """Anchors that keep the whole footprint inside ``zone``."""
        out: list[Anchor] = []
        for rotation in ROTATIONS:
            w, h = rotated_size(block.width, block.height, rotation)
            out += [
                (x, y, rotation)
                for y in range(zone[1], zone[3] - h + 1)
                for x in range(zone[0], zone[2] - w + 1)
            ]
        return out

    def _holding_anchors(self, unit: Block, members: list[Block]) -> list[Anchor]:
        """Anchors for a Gas Dispersing Unit whose zone still holds every placed member."""
        rects = [r for b in members for r in (b.rect(),)]
        mx0 = min(r[0] for r in rects)
        my0 = min(r[1] for r in rects)
        mx1 = max(r[2] for r in rects)
        my1 = max(r[3] for r in rects)
        half, offset = ZONE_SIDE // 2, unit.width // 2
        return [
            (x, y, 0)
            for y in range(my1 - 1 - half - offset, my0 + half - offset + 1)
            for x in range(mx1 - 1 - half - offset, mx0 + half - offset + 1)
        ]

    def frontier_anchors(self, block_id: str) -> list[Anchor]:
        """Anchors along the edges of what is already placed, for a block with no placed
        partner; the area's own corner when nothing is placed at all."""
        block = self.blocks[block_id]
        if not self.placed:
            return self._origin_anchors(block)
        x0, y0, x1, y1 = self.bbox()
        out: list[Anchor] = []
        for rotation in ROTATIONS:
            w, h = (
                (block.width, block.height)
                if rotation % 180 == 0
                else (block.height, block.width)
            )
            out += [(x, y1, rotation) for x in range(x0, x1 + 1)]
            out += [(x, y0 - h, rotation) for x in range(x0, x1 + 1)]
            out += [(x1, y, rotation) for y in range(y0, y1 + 1)]
            out += [(x0 - w, y, rotation) for y in range(y0, y1 + 1)]
        return out
