"""Net routing: wires between pins, trees with splitters and convergers, bridges, repeaters.

Each net becomes wires: a sink takes its whole demand from one source when a source has the
room (best fit), else it is split over sources; a pipe net with several sources and several
sinks becomes a trunk from its largest source to its largest sink that the other sources join
before the other sinks branch off, so even splitters deliver the planned rates (game-knowledge
JCT-01, JCT-02). Wires of one source form a tree: a later wire may branch from a straight
interior cell of an earlier wire (a splitter goes there); wires into one sink join its tree the
same way (a converger). Paths are found by ``pathfinder.astar`` on the wire's layer; overused
cells are ripped up and rerouted with a rising present cost (negotiated congestion); ripping a
wire also rips the wires that branch from or join into it. Belts stay inside the area, pipes may
cross the ring (LOG-08). The result is written into a layout as units and segments.
"""

from fractions import Fraction

from kohakuefda.layout.assemble import PortOption, WorldPin
from kohakuefda.model.cells import Netlist
from kohakuefda.model.control import Cancelled, CancelledError, Observe
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.geometry import Edge, rotate_edge
from kohakuefda.model.layout import Cell, Layout, Segment, Unit
from kohakuefda.model.machines import GROUND, SKY
from kohakuefda.model.plan import Finding
from kohakuefda.route.grid import occupancy_of
from kohakuefda.route.pathfinder import (
    BRIDGE_COST,
    HISTORY_COST,
    OPPOSITE,
    TURN_COST,
    RouteGrid,
    astar,
)

PinKey = tuple[str, str]
WireState = tuple["Wire", list[Cell], Cell | None, Cell | None]
LAYER = {"belt": GROUND, "pipe": SKY}
SPLITTER = {"belt": "log_splitter", "pipe": "log_pipe_splitter"}
CONVERGER = {"belt": "log_converger", "pipe": "log_pipe_converger"}
BRIDGE = {"belt": "log_connector", "pipe": "log_pipe_connector"}
MAX_ITERATIONS = 40
DETOUR = 2.5
SLACK = 16.0
PRESENT_COST = 2.0
PRESENT_GROWTH = 1.5
HEADINGS = {(1, 0): Edge.E, (-1, 0): Edge.W, (0, 1): Edge.S, (0, -1): Edge.N}
ROLE_ORDER = {"trunk": 0, "join": 1, "plain": 2, "branch": 3}
Supply = tuple[PinKey, Fraction]


class RoutingError(RuntimeError):
    """A wire could not be routed or congestion could not be resolved."""


class Wire:
    """One source pin → one sink pin flow of a net.

    ``role`` is ``plain``, or in a trunk net ``trunk`` (largest source to largest sink),
    ``join`` (another source into the trunk) or ``branch`` (the trunk to another sink).
    """

    def __init__(
        self,
        wire_id: str,
        net_id: str,
        kind: str,
        source: PinKey,
        sink: PinKey,
        rate: Fraction,
        role: str = "plain",
        item_id: str | None = None,
    ) -> None:
        self.id = wire_id
        self.net_id = net_id
        self.kind = kind
        self.source = source
        self.sink = sink
        self.rate = rate
        self.role = role
        self.item_id = item_id
        self.cells: list[Cell] = []
        self.branch: Cell | None = None
        self.join: Cell | None = None
        self.source_port: PortOption | None = None
        self.sink_port: PortOption | None = None

    @property
    def layer(self) -> int:
        return LAYER[self.kind]

    @property
    def routed(self) -> bool:
        return bool(self.cells) or (self.branch is not None and self.join is not None)


def _direction(a: Cell, b: Cell) -> Edge:
    return HEADINGS[(b[0] - a[0], b[1] - a[1])]


def assign(
    sources: list[Supply],
    sinks: list[Supply],
    positions: dict[PinKey, Cell] | None = None,
) -> list[tuple[PinKey, PinKey, Fraction]]:
    """Best-fit assignment: the largest sinks first, each whole from the source with the
    least room that still holds it and, among those, the one whose pin is nearest."""

    def distance(source: PinKey, sink: PinKey) -> int:
        if positions is None:
            return 0
        a, b = positions.get(source), positions.get(sink)
        if a is None or b is None:
            return 0
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    room: dict[PinKey, Fraction] = {}
    for key, rate in sources:
        room[key] = room.get(key, Fraction(0)) + rate
    out: list[tuple[PinKey, PinKey, Fraction]] = []
    for sink, demand in sorted(sinks, key=lambda s: -s[1]):
        holders = [k for k, left in room.items() if left >= demand]
        if holders:
            best = min(holders, key=lambda k: (room[k], distance(k, sink)))
            out.append((best, sink, demand))
            room[best] -= demand
            continue
        remaining = demand
        for key in list(room):
            if remaining <= 0:
                break
            take = min(room[key], remaining)
            if take > 0:
                out.append((key, sink, take))
                room[key] -= take
                remaining -= take
    return out


def wires_of(
    netlist: Netlist, positions: dict[PinKey, Cell] | None = None
) -> list[Wire]:
    """The wires of every net: best-fit pairs, or a trunk with joins and branches for a
    pipe net that has several sources and several sinks. With pin ``positions`` the sources
    and sinks are taken in reading order, so equal demands pair with their nearest lane.
    """
    wires: list[Wire] = []

    def ordered(refs) -> list[Supply]:
        out = [((r.cell_id, r.pin_id), r.rate) for r in refs if r.rate > 0]
        if positions is not None:
            out.sort(key=lambda s: positions.get(s[0], (0, 0)))
        return out

    def add(net, source: PinKey, sink: PinKey, rate: Fraction, role: str) -> None:
        wires.append(
            Wire(
                f"w{len(wires)}",
                net.id,
                net.kind,
                source,
                sink,
                rate,
                role,
                net.item_id,
            )
        )

    for net in netlist.nets:
        sources = ordered(net.sources)
        sinks = ordered(net.sinks)
        if net.kind == "pipe" and len(sources) > 1 and len(sinks) > 1:
            root, root_rate = max(sources, key=lambda s: s[1])
            main, _ = max(sinks, key=lambda s: s[1])
            add(net, root, main, root_rate, "trunk")
            for key, rate in sources:
                if key != root:
                    add(net, key, main, rate, "join")
            for key, rate in sinks:
                if key != main:
                    add(net, root, key, rate, "branch")
            continue
        for source, sink, rate in assign(sources, sinks, positions):
            add(net, source, sink, rate, "plain")
    return wires


def ring_cells(width: int, height: int, area: tuple[int, int, int, int]) -> set[Cell]:
    """Grid cells outside ``area``: closed to belts, open to pipes."""
    x0, y0, x1, y1 = area
    return {
        (x, y)
        for y in range(height)
        for x in range(width)
        if not (x0 <= x < x1 and y0 <= y < y1)
    }


def grid_of(
    dataset: Dataset,
    layout: Layout,
    turn_cost: float = TURN_COST,
    bridge_cost: float = BRIDGE_COST,
    history_cost: float = HISTORY_COST,
) -> RouteGrid:
    """A routing grid blocked by everything already in ``layout`` and, for belts, the ring."""
    occupancy = occupancy_of(dataset, layout)
    blocked = [
        {
            (x, y)
            for y in range(layout.height)
            for x in range(layout.width)
            if occupancy.grid[layer, y, x]
        }
        for layer in (GROUND, SKY)
    ]
    blocked[GROUND] |= ring_cells(layout.width, layout.height, layout.area_rect)
    return RouteGrid(
        layout.width, layout.height, blocked, turn_cost, bridge_cost, history_cost
    )


class Router:
    """Routes every wire over a grid; ``emit`` writes units and segments into a layout."""

    def __init__(
        self,
        dataset: Dataset,
        grid: RouteGrid,
        pins: dict[PinKey, WorldPin],
        wires: list[Wire],
        present_cost: float = PRESENT_COST,
        present_growth: float = PRESENT_GROWTH,
        max_iterations: int = MAX_ITERATIONS,
    ) -> None:
        self.dataset = dataset
        self.grid = grid
        self.pins = pins
        self.wires = wires
        self.present_cost = present_cost
        self.present_growth = present_growth
        self.max_iterations = max_iterations
        self.taken: dict[str, set[int]] = {}
        for wire in self.wires:
            for key in (wire.source, wire.sink):
                self.reserve_pin(key, wire)
        self.trees: dict[tuple[str, PinKey], list[Wire]] = {}
        self.failed: list[Wire] = []
        self.findings: list[Finding] = []
        self.recording: dict[str, WireState] | None = None
        self.ripped_now: list[Wire] = []
        self.forced: set[str] = set()
        self.share = True
        self.detour = DETOUR
        self.slack = SLACK

    def reserve_pin(self, key: PinKey, wire: Wire) -> None:
        """Close a pin's only facing cell to every wire but this one; nothing to do while the
        pin's block is unplaced or the lane may pick another port."""
        pin = self.pins.get(key)
        if pin is not None and len(pin.options) == 1:
            self.grid.reserve(LAYER[pin.kind], pin.outside, wire.id)

    def unreserve_pin(self, key: PinKey, wire: Wire) -> None:
        pin = self.pins.get(key)
        if pin is not None and len(pin.options) == 1:
            self.grid.unreserve(LAYER[pin.kind], pin.outside, wire.id)

    def _slot(self, key: PinKey) -> str:
        """Ports are numbered per direction, so a machine's IN and OUT ports are claimed
        apart."""
        return f"{key[0]}:{self.pins[key].direction}"

    def options(self, key: PinKey, wire: Wire) -> list[PortOption]:
        """Ports the wire may still use at ``key``: those no other wire of the machine has
        taken, whose facing cell is on the grid and free of buildings."""
        pin = self.pins[key]
        layer = LAYER[pin.kind]
        used = self.taken.get(self._slot(key), set())
        mine = {p.index for p in (wire.source_port, wire.sink_port) if p is not None}
        out = []
        for option in pin.options:
            if option.index in used and option.index not in mine:
                continue
            if self.grid.is_blocked(layer, option.outside):
                continue
            out.append(option)
        return out

    def _claim(self, key: PinKey, option: PortOption) -> None:
        self.taken.setdefault(self._slot(key), set()).add(option.index)

    def _release(self, key: PinKey, option: PortOption | None) -> None:
        if option is not None:
            self.taken.get(self._slot(key), set()).discard(option.index)

    def source_cell(self, wire: Wire) -> Cell:
        """The port cell the wire leaves from, or its branch on the tree."""
        port = wire.source_port or self.pins[wire.source].default
        return port.cell

    def sink_cell(self, wire: Wire) -> Cell:
        port = wire.sink_port or self.pins[wire.sink].default
        return port.cell

    def _record(self, wire: Wire) -> None:
        """Remember a wire's path before it changes, while a recording is open."""
        if self.recording is not None and wire.id not in self.recording:
            self.recording[wire.id] = (wire, list(wire.cells), wire.branch, wire.join)

    def _tree(self, net_id: str, key: PinKey) -> list[Wire]:
        return self.trees.setdefault((net_id, key), [])

    def _straight_cells(self, wires: list[Wire], layer: int) -> dict[Cell, Edge]:
        """Straight cells of routed wires with their travel direction, the cells in front of
        the ports included (a unit there links to the port directly)."""
        out: dict[Cell, Edge] = {}
        for wire in wires:
            if len(wire.cells) < 2:
                continue
            chain = [
                wire.branch or self.source_cell(wire),
                *wire.cells,
                wire.join or self.sink_cell(wire),
            ]
            for index in range(1, len(chain) - 1):
                before, cell, after = chain[index - 1 : index + 2]
                straight = before[0] == after[0] or before[1] == after[1]
                free = (
                    not self.grid.has_unit(layer, cell)
                    and len(self.grid.holders_at(layer, cell)) == 1
                )
                if layer == SKY and not self.grid.ground_free(cell):
                    free = False
                if straight and free:
                    out[cell] = _direction(cell, after)
        return out

    def _trunk_bounds(self, trunk: Wire) -> tuple[int, int]:
        """On a trunk: the index after the last join and the index of the first branch."""
        last_join = -1
        first_branch = len(trunk.cells)
        for other in self._tree(trunk.net_id, trunk.sink):
            if other is not trunk and other.join in trunk.cells:
                last_join = max(last_join, trunk.cells.index(other.join))
        for other in self._tree(trunk.net_id, trunk.source):
            if other is not trunk and other.branch in trunk.cells:
                first_branch = min(first_branch, trunk.cells.index(other.branch))
        return last_join, first_branch

    def _ends(
        self, wire: Wire, key: PinKey
    ) -> tuple[dict[Cell, set[Edge] | None], dict[Cell, Edge]]:
        """Cells a wire may start from or end on at ``key``: the pin's free cell when no
        tree exists there, else straight cells of the tree; joins stay upstream of every
        branch of a trunk and branches downstream of every join."""
        tree = [w for w in self._tree(wire.net_id, key) if w.cells and w is not wire]
        if not tree:
            return {o.outside: None for o in self.options(key, wire)}, {}
        straight = self._straight_cells(tree, wire.layer)
        for trunk in tree:
            if trunk.role != "trunk":
                continue
            last_join, first_branch = self._trunk_bounds(trunk)
            if wire.role == "join":
                cut = trunk.cells[first_branch:]
            elif wire.role == "branch" or key == wire.source:
                cut = trunk.cells[: last_join + 1]
            else:
                cut = []
            for cell in cut:
                straight.pop(cell, None)
        ends: dict[Cell, set[Edge] | None] = {}
        for cell, travel in straight.items():
            ends[cell] = {
                e for e in Edge if e is not travel and e is not OPPOSITE[travel]
            }
        return ends, straight

    def _blockers(self, wire: Wire) -> list[Wire]:
        """On a trunk, the attachments that keep this join or branch off it: the branches
        for a join, the joins for a branch."""
        if wire.role not in ("join", "branch"):
            return []
        key = wire.sink if wire.role == "join" else wire.source
        out: list[Wire] = []
        for trunk in self._tree(wire.net_id, key):
            if trunk.role != "trunk":
                continue
            if wire.role == "join":
                others = self._tree(wire.net_id, trunk.source)
                out += [o for o in others if o is not trunk and o.branch in trunk.cells]
            else:
                others = self._tree(wire.net_id, trunk.sink)
                out += [o for o in others if o is not trunk and o.join in trunk.cells]
        return out

    def budget(self, starts: dict, goals: dict) -> float:
        """What a path between these ends may cost before it is not worth having: the
        shortest distance across stretched by ``detour``, plus ``slack`` cells to turn in.
        A path dearer than that would be long enough to cost more floor than it is worth.
        """
        if not starts or not goals:
            return 0.0
        span = min(abs(a[0] - b[0]) + abs(a[1] - b[1]) for a in starts for b in goals)
        return self.slack + self.detour * span

    def _route_wire(self, wire: Wire, present_cost: float) -> bool:
        """Route one wire; a join or branch that the trunk's other attachments leave no
        room for rips them first (they queue for rerouting) and tries again."""
        self._record(wire)
        starts, branch_dirs = self._ends(wire, wire.source)
        goals, join_dirs = self._ends(wire, wire.sink)
        path = astar(
            self.grid,
            wire.layer,
            wire.id,
            starts,
            goals,
            present_cost,
            self.share,
            self.budget(starts, goals),
            set(join_dirs),
        )
        if path is None:
            blockers = self._blockers(wire) if wire.id not in self.forced else []
            if not blockers:
                return False
            self.forced.add(wire.id)
            for blocker in blockers:
                self.ripped_now += [
                    w for w in self.rip(blocker) if w not in self.ripped_now
                ]
            starts, branch_dirs = self._ends(wire, wire.source)
            goals, join_dirs = self._ends(wire, wire.sink)
            path = astar(
                self.grid,
                wire.layer,
                wire.id,
                starts,
                goals,
                present_cost,
                self.share,
                self.budget(starts, goals),
                set(join_dirs),
            )
            if path is None:
                return False
        wire.branch = path[0] if path[0] in branch_dirs else None
        wire.join = path[-1] if path[-1] in join_dirs else None
        if wire.branch is None:
            source_port = self._option_at(wire.source, wire, path[0])
            if source_port is None:
                return False
            wire.source_port = source_port
            self._claim(wire.source, source_port)
        if wire.join is None:
            sink_port = self._option_at(wire.sink, wire, path[-1])
            if sink_port is None:
                self._release(wire.source, wire.source_port)
                wire.source_port = None
                return False
            wire.sink_port = sink_port
            self._claim(wire.sink, sink_port)
        cells = path[1:] if wire.branch else path
        cells = cells[:-1] if wire.join else cells
        if wire.branch is not None:
            self.grid.add_unit(wire.layer, wire.branch)
        if wire.join is not None:
            self.grid.add_unit(wire.layer, wire.join)
        wire.cells = cells
        self.hold(wire)
        self._tree(wire.net_id, wire.source).append(wire)
        self._tree(wire.net_id, wire.sink).append(wire)
        return True

    def _option_at(self, key: PinKey, wire: Wire, cell: Cell) -> PortOption | None:
        """The port of ``key`` whose facing cell is ``cell``."""
        return next((o for o in self.options(key, wire) if o.outside == cell), None)

    def hold(self, wire: Wire) -> None:
        """Register the wire's cells on the grid with the port or tree cell at each end."""
        before = wire.branch or self.source_cell(wire)
        after = wire.join or self.sink_cell(wire)
        self.grid.add_wire(wire.layer, wire.id, wire.cells, before, after)

    def dependants(self, wire: Wire) -> list[Wire]:
        """Wires that branch from or join into ``wire``'s cells."""
        cells = set(wire.cells)
        out: list[Wire] = []
        for key in ((wire.net_id, wire.source), (wire.net_id, wire.sink)):
            for other in self.trees.get(key, []):
                if other is wire or other in out:
                    continue
                if other.branch in cells or other.join in cells:
                    out.append(other)
        return out

    def rip(self, wire: Wire) -> list[Wire]:
        """Rip ``wire`` and everything hanging from it; returns every wire ripped."""
        ripped: list[Wire] = []
        pending = [wire]
        while pending:
            current = pending.pop()
            if current in ripped:
                continue
            pending.extend(self.dependants(current))
            self._rip_one(current)
            ripped.append(current)
        return ripped

    def _rip_one(self, wire: Wire) -> None:
        self._record(wire)
        self.grid.remove_wire(wire.layer, wire.id, wire.cells)
        if wire.branch is not None:
            self.grid.discard_unit(wire.layer, wire.branch)
        if wire.join is not None:
            self.grid.discard_unit(wire.layer, wire.join)
        self._release(wire.source, wire.source_port)
        self._release(wire.sink, wire.sink_port)
        wire.source_port = None
        wire.sink_port = None
        wire.cells = []
        wire.branch = None
        wire.join = None
        for key in ((wire.net_id, wire.source), (wire.net_id, wire.sink)):
            if wire in self.trees.get(key, []):
                self.trees[key].remove(wire)

    def overused(self) -> set[tuple[int, Cell]]:
        return {
            (layer, cell)
            for layer in (GROUND, SKY)
            for cell in self.grid.overused(layer)
        }

    def length(self) -> int:
        return sum(len(w.cells) for w in self.wires)

    def frame(
        self,
        kind: str,
        iteration: int,
        present: float,
        routed: int,
        overused: set[tuple[int, Cell]],
    ) -> dict:
        return {
            "kind": kind,
            "iteration": iteration,
            "present": present,
            "routed": routed,
            "total": len(self.wires),
            "wires": [[w.id, w.kind, w.net_id, w.cells] for w in self.wires if w.cells],
            "overused": [[layer, cell[0], cell[1]] for layer, cell in overused],
            "failed": [w.id for w in self.failed],
        }

    def order(self) -> list[Wire]:
        """Pipes first; trunks, then joins, plain wires, branches; then by rate, the
        farthest sink of a source first so that later wires of the tree can branch."""

        def span(wire: Wire) -> int:
            a = self.pins[wire.source].outside
            b = self.pins[wire.sink].outside
            return abs(a[0] - b[0]) + abs(a[1] - b[1])

        return sorted(
            self.wires,
            key=lambda w: (w.kind != "pipe", ROLE_ORDER[w.role], -w.rate, -span(w)),
        )

    def route(
        self,
        observe: Observe | None = None,
        cancelled: Cancelled | None = None,
        strict: bool = True,
        pending: list[Wire] | None = None,
    ) -> bool:
        """Negotiated congestion: route, rip up overused cells' wires, raise the present cost.

        ``observe`` gets a ``wire`` frame after every routed wire and a ``pass`` frame after
        every negotiation pass. When ``strict`` a wire still without a path once congestion
        is settled, or congestion that never settles, raises ``RoutingError``; otherwise the
        result says whether everything routed clean and ``failed`` lists the wires without a
        path.
        """
        order = self.order()
        pending = list(pending) if pending is not None else list(order)
        scope = set(pending)
        present = self.present_cost
        for iteration in range(self.max_iterations):
            self.failed = [w for w in self.failed if w not in pending]
            self.forced = set()
            queue = list(pending)
            position = 0
            while position < len(queue):
                wire = queue[position]
                position += 1
                if cancelled is not None and cancelled():
                    raise CancelledError("routing cancelled")
                self.ripped_now = []
                routed_ok = self._route_wire(wire, present)
                for extra in self.ripped_now:
                    if extra not in queue[position:]:
                        queue.append(extra)
                        self.failed = [w for w in self.failed if w is not extra]
                if not routed_ok:
                    self.failed.append(wire)
                elif observe is not None:
                    routed = sum(1 for w in self.wires if w.cells)
                    observe(self.frame("wire", iteration, present, routed, set()))
            pending = queue
            scope |= set(queue)
            overused = self.overused()
            if observe is not None:
                observe(
                    self.frame("pass", iteration, present, len(self.wires), overused)
                )
            unresolved = [w for w in self.failed if w in scope]
            if not overused:
                if unresolved and strict:
                    wire = unresolved[0]
                    raise RoutingError(
                        f"no path for {wire.id} ({wire.kind} {wire.net_id})"
                    )
                return not unresolved
            for layer, cell in overused:
                self.grid.charge(
                    layer, cell, self.grid.history[layer].get(cell, 0.0) + 1.0
                )
            pending = []
            for wire in order:
                if wire in unresolved or any(
                    (wire.layer, c) in overused for c in wire.cells
                ):
                    pending.append(wire)
            ripped: list[Wire] = []
            for wire in pending:
                if wire.cells or wire.branch is not None:
                    ripped += self.rip(wire)
            pending = [w for w in order if w in pending or w in ripped]
            scope |= set(pending)
            present *= self.present_growth
        for wire in pending:
            if not self._route_wire(wire, present) and wire not in self.failed:
                self.failed.append(wire)
        if strict:
            raise RoutingError("congestion could not be resolved")
        return False

    def unrouted(self) -> list[Wire]:
        """Wires without a path: no cells and no branch or join."""
        return [
            w for w in self.wires if not w.cells and w.branch is None and w.join is None
        ]

    def _travel_at(self, wire: Wire, cell: Cell) -> Edge:
        """Direction of travel at ``cell``: toward the next cell, or into the join or the
        sink's port after the last one."""
        index = wire.cells.index(cell)
        if index + 1 < len(wire.cells):
            return _direction(cell, wire.cells[index + 1])
        return _direction(cell, wire.join or self.sink_cell(wire))

    def _entry_at(self, wire: Wire, cell: Cell) -> Edge:
        """Direction of travel into ``cell``: from the cell before it, or from the branch or
        the source's port before the first one."""
        index = wire.cells.index(cell)
        if index > 0:
            return _direction(wire.cells[index - 1], cell)
        return _direction(wire.branch or self.source_cell(wire), cell)

    def _parent_at(self, net_id: str, key: PinKey, cell: Cell, layer: int) -> Wire:
        for wire in self._tree(net_id, key):
            if cell in wire.cells:
                return wire
        raise RoutingError(f"no parent wire at {cell} on layer {layer}")

    def emit(self, layout: Layout) -> None:
        """Units at branches, joins and crossings; segments for every routed wire piece; pin
        extensions. A wire without a path contributes nothing."""
        self.layout = layout
        routed = [w for w in self.wires if w.routed]
        cut: dict[str, set[Cell]] = {w.id: set() for w in routed}
        for wire in routed:
            if wire.branch is not None:
                parent = self._parent_at(
                    wire.net_id, wire.source, wire.branch, wire.layer
                )
                travel = self._travel_at(parent, wire.branch)
                rotation = next(
                    r
                    for r in (0, 90, 180, 270)
                    if rotate_edge(Edge.N, r) is OPPOSITE[travel]
                )
                self._unit(
                    f"{wire.id}:split", SPLITTER[wire.kind], wire.branch, rotation
                )
                cut[parent.id].add(wire.branch)
            if wire.join is not None:
                parent = self._parent_at(wire.net_id, wire.sink, wire.join, wire.layer)
                travel = self._travel_at(parent, wire.join)
                rotation = next(
                    r for r in (0, 90, 180, 270) if rotate_edge(Edge.S, r) is travel
                )
                self._unit(f"{wire.id}:join", CONVERGER[wire.kind], wire.join, rotation)
                cut[parent.id].add(wire.join)
        bridged: set[tuple[int, Cell]] = set()
        for wire in routed:
            for cell in wire.cells:
                holders = self.grid.holders_at(wire.layer, cell)
                if len(holders) == 2 and (wire.layer, cell) not in bridged:
                    bridged.add((wire.layer, cell))
                    self._unit(
                        f"bridge:{cell[0]}:{cell[1]}:{wire.kind}",
                        BRIDGE[wire.kind],
                        cell,
                        0,
                    )
                    for holder in holders:
                        cut.setdefault(holder, set()).add(cell)
        for wire in routed:
            self._emit_wire(wire, cut[wire.id])

    def _unit(self, unit_id: str, spec: str, cell: Cell, rotation: int) -> None:
        self.layout.units.append(
            Unit(id=unit_id, unit_id=spec, x=cell[0], y=cell[1], rotation=rotation)
        )

    def _emit_wire(self, wire: Wire, cuts: set[Cell]) -> None:
        pieces: list[list[Cell]] = []
        current: list[Cell] = []
        for cell in wire.cells:
            if cell in cuts:
                if current:
                    pieces.append(current)
                current = []
            else:
                current.append(cell)
        if current:
            pieces.append(current)
        limit = (
            self.dataset.constants.pipe_run_max
            if wire.kind == "pipe"
            else self.dataset.constants.belt_run_max
        )
        pieces = self._repeat(wire, pieces, limit)
        source_cell = self.source_cell(wire)
        sink_cell = self.sink_cell(wire)
        for index, piece in enumerate(pieces):
            first = index == 0 and wire.branch is None
            last = index == len(pieces) - 1 and wire.join is None
            if (
                first
                and wire.source_port is not None
                and piece[0] == wire.source_port.outside
            ):
                segment = self._segment_ending(source_cell, wire.kind)
                if segment is not None:
                    segment.cells = segment.cells + piece
                    if (
                        last
                        and wire.sink_port is not None
                        and piece[-1] == wire.sink_port.outside
                    ):
                        tail = self._segment_starting(sink_cell, wire.kind)
                        if tail is not None:
                            segment.cells = segment.cells + tail.cells
                            self.layout.segments.remove(tail)
                    continue
            if (
                last
                and wire.sink_port is not None
                and piece[-1] == wire.sink_port.outside
            ):
                segment = self._segment_starting(sink_cell, wire.kind)
                if segment is not None:
                    segment.cells = piece + segment.cells
                    continue
            self.layout.segments.append(
                Segment(
                    id=f"{wire.id}:p{index}",
                    kind=wire.kind,
                    cells=piece,
                    heading=self._travel_at(wire, piece[-1]),
                    entry=self._entry_at(wire, piece[0]),
                    item_id=wire.item_id,
                )
            )

    def _repeat(
        self, wire: Wire, pieces: list[list[Cell]], limit: int
    ) -> list[list[Cell]]:
        """Cut pieces longer than the run limit with a repeater splitter at a straight cell."""
        out: list[list[Cell]] = []
        for piece in pieces:
            while len(piece) > limit:
                index = limit - 1
                while index > 1 and not self._straight(wire, piece[index]):
                    index -= 1
                cell = piece[index]
                travel = self._travel_at(wire, cell)
                rotation = next(
                    r
                    for r in (0, 90, 180, 270)
                    if rotate_edge(Edge.N, r) is OPPOSITE[travel]
                )
                self._unit(
                    f"{wire.id}:rep{cell[0]}_{cell[1]}",
                    SPLITTER[wire.kind],
                    cell,
                    rotation,
                )
                out.append(piece[:index])
                piece = piece[index + 1 :]
            out.append(piece)
        return out

    def _straight(self, wire: Wire, cell: Cell) -> bool:
        index = wire.cells.index(cell)
        if index == 0 or index == len(wire.cells) - 1:
            return False
        before, after = wire.cells[index - 1], wire.cells[index + 1]
        return before[0] == after[0] or before[1] == after[1]

    def _segment_ending(self, cell: Cell, kind: str) -> Segment | None:
        return next(
            (
                s
                for s in self.layout.segments
                if s.kind == kind and s.cells and s.cells[-1] == cell
            ),
            None,
        )

    def _segment_starting(self, cell: Cell, kind: str) -> Segment | None:
        return next(
            (
                s
                for s in self.layout.segments
                if s.kind == kind and s.cells and s.cells[0] == cell
            ),
            None,
        )


def route_layout(
    dataset: Dataset,
    layout: Layout,
    pins: dict[PinKey, WorldPin],
    netlist: Netlist,
    observe: Observe | None = None,
    cancelled: Cancelled | None = None,
    present_cost: float = PRESENT_COST,
    present_growth: float = PRESENT_GROWTH,
    max_iterations: int = MAX_ITERATIONS,
    turn_cost: float = TURN_COST,
    bridge_cost: float = BRIDGE_COST,
    history_cost: float = HISTORY_COST,
) -> list[Wire]:
    """Route every net of ``netlist`` into ``layout``; raises ``RoutingError`` when it cannot."""
    grid = grid_of(dataset, layout, turn_cost, bridge_cost, history_cost)
    router = Router(
        dataset,
        grid,
        pins,
        wires_of(netlist),
        present_cost,
        present_growth,
        max_iterations,
    )
    router.route(observe, cancelled)
    router.emit(layout)
    return router.wires
