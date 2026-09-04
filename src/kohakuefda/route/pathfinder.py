"""A* over one layer of the routing grid with soft congestion and legal crossings.

A path enters a cell held by another wire of its kind only as a crossing: that wire must run
straight through the cell perpendicular to the move, at most one other wire may be there, and
the path must leave the cell straight on. Any other sharing costs the present congestion
penalty times the cell's history; history itself is charged on every entry, so that later
iterations negotiate contested cells away. Cells reserved for particular wires (the cells pins
face) are closed to every other wire except as a crossing of the owner's routed path (a bridge
in front of the port). The heuristic is the Manhattan distance to the bounding box of the goal
cells.
"""

import heapq
import logging

from kohakuefda.model.geometry import Edge
from kohakuefda.model.layout import Cell, Rect

try:
    from kohakuefda._native import _Grid

    NATIVE = True
except ImportError:  # the pure-Python search below stands in
    _Grid = None
    NATIVE = False

log = logging.getLogger(__name__)
Axis = str
OPPOSITE = {Edge.N: Edge.S, Edge.S: Edge.N, Edge.E: Edge.W, Edge.W: Edge.E}
AXIS_OF = {Edge.N: "v", Edge.S: "v", Edge.E: "h", Edge.W: "h"}
STEPS: tuple[tuple[Edge, int, int], ...] = (
    (Edge.N, 0, -1),
    (Edge.E, 1, 0),
    (Edge.S, 0, 1),
    (Edge.W, -1, 0),
)
TURN_COST = 0.1
BRIDGE_COST = 4.0
HISTORY_COST = 1.0
AXIS_CODE = {"h": 1, "v": 2, "t": 3}
AXIS_NAME = {code: name for name, code in AXIS_CODE.items()}
STEP_BIT = {edge: 1 << index for index, (edge, _, _) in enumerate(STEPS)}


class RouteGrid:
    """Occupancy of wires per layer: who holds a cell and along which axis."""

    def __init__(
        self,
        width: int,
        height: int,
        blocked: list[set[Cell]],
        turn_cost: float = TURN_COST,
        bridge_cost: float = BRIDGE_COST,
        history_cost: float = HISTORY_COST,
    ) -> None:
        self.width = width
        self.height = height
        self.blocked = blocked
        self.turn_cost = turn_cost
        self.bridge_cost = bridge_cost
        self.history_cost = history_cost
        self.holders: list[dict[Cell, dict[str, Axis]]] = [{}, {}]
        self.history: list[dict[Cell, float]] = [{}, {}]
        self.owned: list[set[Cell]] = [set(), set()]
        self.units: list[set[Cell]] = [set(), set()]
        self.reserved: list[dict[Cell, set[str]]] = [{}, {}]
        self._wires: dict[str, int] = {}
        self._names: dict[int, str] = {}
        self.native = (
            _Grid(width, height, turn_cost, bridge_cost, history_cost)
            if _Grid is not None
            else None
        )
        for layer, cells in enumerate(blocked):
            self.push(layer)
            for cell in cells:
                self._mirror("block", layer, cell, True)

    # ---- the mirror -----------------------------------------------------

    def _code(self, wire_id: str) -> int:
        """A small integer per wire, since the native grid keys on numbers."""
        code = self._wires.get(wire_id)
        if code is None:
            code = len(self._wires)
            self._wires[wire_id] = code
            self._names[code] = wire_id
        return code

    def _mirror(self, call: str, layer: int, cell: Cell, *args) -> None:
        if self.native is not None:
            getattr(self.native, call)(layer, cell[0], cell[1], *args)

    def python_state(self) -> tuple | None:
        """The occupancy Python still keeps, for a snapshot; ``None`` when the native grid
        holds it all and :meth:`save` covers it."""
        if self.native is not None:
            return None
        return (
            [{c: dict(h) for c, h in layer.items()} for layer in self.holders],
            [set(layer) for layer in self.units],
            [set(layer) for layer in self.blocked],
            [set(layer) for layer in self.owned],
            [{c: set(o) for c, o in layer.items()} for layer in self.reserved],
        )

    def restore_python(self, state: tuple | None) -> None:
        """Put back what :meth:`python_state` took."""
        if state is None:
            return
        self.holders = [{c: dict(h) for c, h in layer.items()} for layer in state[0]]
        self.units = [set(layer) for layer in state[1]]
        self.blocked = [set(layer) for layer in state[2]]
        self.owned = [set(layer) for layer in state[3]]
        self.reserved = [{c: set(o) for c, o in layer.items()} for layer in state[4]]

    def save(self) -> object | None:
        """The native occupancy put by, to come back to with :meth:`load`."""
        return None if self.native is None else self.native.save()

    def load(self, state: object | None) -> None:
        """Come back to a saved native occupancy, instead of rebuilding it cell by cell."""
        if self.native is not None and state is not None:
            self.native.load_state(state)

    def push(self, layer: int) -> None:
        """Hand one layer to the native grid whole, after the Python side was replaced."""
        if self.native is None:
            return
        self.native.load(
            layer,
            list(self.blocked[layer]),
            list(self.owned[layer]),
            list(self.units[layer]),
            [
                (cell[0], cell[1], self._code(wire), AXIS_CODE[axis])
                for cell, holders in self.holders[layer].items()
                for wire, axis in holders.items()
            ],
            [
                (cell[0], cell[1], [self._code(w) for w in owners])
                for cell, owners in self.reserved[layer].items()
            ],
            [(cell[0], cell[1], value) for cell, value in self.history[layer].items()],
        )

    def block(self, layer: int, cell: Cell, owned: bool = False) -> None:
        """Close a cell to every lane; ``owned`` marks it a machine's own footprint rather
        than the ring or the fixed depot, which the line is not measured by."""
        self.blocked[layer].add(cell)
        self._mirror("block", layer, cell, True)
        if owned:
            self.owned[layer].add(cell)
            self._mirror("own", layer, cell, True)

    def unblock(self, layer: int, cell: Cell) -> None:
        self.blocked[layer].discard(cell)
        self.owned[layer].discard(cell)
        self._mirror("block", layer, cell, False)
        self._mirror("own", layer, cell, False)

    def extent(self) -> tuple[int, int, int, int] | None:
        """The rectangle the line needs, or ``None`` when the native grid is not built."""
        return None if self.native is None else self.native.extent()

    def free_square(
        self,
        window: tuple[int, int, int, int],
        size: int,
        taken: list[Cell] | None = None,
    ) -> Cell | None:
        """The first free square of ``size`` inside ``window`` that is not already ``taken``:
        where a pylon may stand."""
        if self.native is None:
            return None
        return self.native.free_square(window, size, taken or [])

    def used(self) -> set[Cell] | None:
        """Every cell the line uses, or ``None`` when the native grid is not built."""
        return None if self.native is None else {tuple(c) for c in self.native.used()}

    # ---- questions asked of the occupancy -------------------------------

    def free_for(self, cells: list[Cell], area: Rect, mine: list[Cell]) -> bool:
        """Whether a footprint fits inside ``area`` clear of every machine but its own."""
        if self.native is not None:
            return self.native.free_for(cells, area, mine)
        blocked, owned = self.blocked[0], set(mine)
        return all(
            area[0] <= x < area[2]
            and area[1] <= y < area[3]
            and ((x, y) not in blocked or (x, y) in owned)
            for x, y in cells
        )

    def is_blocked(self, layer: int, cell: Cell) -> bool:
        """Whether a cell of a layer is closed to every lane."""
        if self.native is not None:
            return self.native.is_blocked(layer, cell[0], cell[1])
        return not self.inside(cell) or cell in self.blocked[layer]

    def first_open(self, layer: int, cells: list[Cell]) -> Cell | None:
        """The first of ``cells`` on ``layer`` that no lane is shut out of."""
        if self.native is not None:
            spot = self.native.first_open(layer, cells)
            return None if spot is None else tuple(spot)
        return next(
            (c for c in cells if self.inside(c) and c not in self.blocked[layer]), None
        )

    def holders_at(self, layer: int, cell: Cell) -> dict[str, Axis]:
        """The wires holding a cell of a layer, with their axis."""
        if self.native is None:
            return self.holders[layer].get(cell, {})
        return {
            self._names[wire]: AXIS_NAME[axis]
            for wire, axis in self.native.holders_at(layer, cell[0], cell[1])
        }

    def has_unit(self, layer: int, cell: Cell) -> bool:
        if self.native is not None:
            return self.native.has_unit(layer, cell[0], cell[1])
        return cell in self.units[layer]

    def add_unit(self, layer: int, cell: Cell) -> None:
        self.units[layer].add(cell)
        self._mirror("unit", layer, cell, True)

    def discard_unit(self, layer: int, cell: Cell) -> None:
        self.units[layer].discard(cell)
        self._mirror("unit", layer, cell, False)

    def charge(self, layer: int, cell: Cell, value: float) -> None:
        """What ``cell`` has been charged for being contested."""
        self.history[layer][cell] = value
        self._mirror("history", layer, cell, value)

    # ---- occupancy ------------------------------------------------------

    def reserve(self, layer: int, cell: Cell, wire_id: str) -> None:
        """Only the named wires may use ``cell`` (a pin's facing cell)."""
        self.reserved[layer].setdefault(cell, set()).add(wire_id)
        self._mirror("reserve_add", layer, cell, self._code(wire_id))

    def unreserve(self, layer: int, cell: Cell, wire_id: str) -> None:
        owners = self.reserved[layer].get(cell)
        if owners is not None:
            owners.discard(wire_id)
            if not owners:
                del self.reserved[layer][cell]
        self._mirror("reserve_drop", layer, cell, self._code(wire_id))

    def inside(self, cell: Cell) -> bool:
        return 0 <= cell[0] < self.width and 0 <= cell[1] < self.height

    def add_wire(
        self,
        layer: int,
        wire_id: str,
        cells: list[Cell],
        before: Cell | None = None,
        after: Cell | None = None,
    ) -> None:
        """Hold ``cells`` for a wire; ``before`` and ``after`` are the cells the path comes
        from and goes on to (a port or a tree cell), so the ends get an axis too."""
        chain = [before, *cells, after]
        held: list[tuple[int, int, int]] = []
        for index, cell in enumerate(cells, start=1):
            prev, nxt = chain[index - 1], chain[index + 1]
            axis = "t"
            if prev is not None and nxt is not None:
                if prev[0] == nxt[0]:
                    axis = "v"
                elif prev[1] == nxt[1]:
                    axis = "h"
            self.holders[layer].setdefault(cell, {})[wire_id] = axis
            held.append((cell[0], cell[1], AXIS_CODE[axis]))
        if self.native is not None and held:
            self.native.hold_many(layer, held, self._code(wire_id))

    def remove_wire(self, layer: int, wire_id: str, cells: list[Cell]) -> None:
        for cell in cells:
            holders = self.holders[layer].get(cell)
            if holders:
                holders.pop(wire_id, None)
                if not holders:
                    del self.holders[layer][cell]
        if self.native is not None and cells:
            self.native.release_many(layer, cells, self._code(wire_id))

    def others(self, layer: int, cell: Cell, wire_id: str) -> dict[str, Axis]:
        return {k: v for k, v in self.holders_at(layer, cell).items() if k != wire_id}

    def legal_crossing(self, layer: int, cell: Cell) -> bool:
        """Exactly two wires, both straight, one per axis, no unit on the cell, and, on the sky
        layer, nothing on the ground under the bridge."""
        if self.native is not None:
            return self.native.legal_crossing(layer, cell[0], cell[1])
        holders = self.holders[layer].get(cell, {})
        return (
            len(holders) == 2
            and set(holders.values()) == {"h", "v"}
            and cell not in self.units[layer]
            and (layer == 0 or self.ground_free(cell))
        )

    def ground_free(self, cell: Cell) -> bool:
        """A pipe unit needs the ground under it: no block, no belt wire."""
        if self.native is not None:
            return self.native.ground_free(cell[0], cell[1])
        return cell not in self.blocked[0] and cell not in self.holders[0]

    def pipe_unit(self, cell: Cell) -> bool:
        """A pipe unit (bridge, splitter, converger) of a routed wire stands on ``cell``."""
        if self.native is not None:
            return self.native.pipe_unit(cell[0], cell[1])
        if cell in self.units[1]:
            return True
        holders = self.holders[1].get(cell)
        return holders is not None and len(holders) == 2

    def overused(self, layer: int) -> list[Cell]:
        if self.native is not None:
            return [tuple(c) for c in self.native.overused(layer)]
        out = [
            cell
            for cell, holders in self.holders[layer].items()
            if len(holders) > 1 and not self.legal_crossing(layer, cell)
        ]
        if layer == 0:
            out += [cell for cell in self.holders[0] if self.pipe_unit(cell)]
        return out


def _crossing_ok(others: dict[str, Axis], direction: Edge) -> bool:
    return len(others) == 1 and next(iter(others.values())) == (
        "h" if AXIS_OF[direction] == "v" else "v"
    )


def astar(
    grid: RouteGrid,
    layer: int,
    wire_id: str,
    starts: dict[Cell, set[Edge] | None],
    goals: dict[Cell, set[Edge] | None],
    present_cost: float,
    share: bool = True,
    limit: float = float("inf"),
    shared: set[Cell] | None = None,
) -> list[Cell] | None:
    """Cheapest path from any start to any goal, or None, on the native grid when it is built
    and in ``search`` below when it is not.

    ``starts`` and ``goals`` map cells to the directions a path may leave or enter them by
    (``None`` for any). A cell that is both is the whole path: the one cell two ports facing
    each other across it need (LOG-11). Without ``share`` a cell another wire holds is closed
    unless the move is a legal crossing. ``limit`` caps what a path may cost; the heuristic
    never overestimates, so a frontier past it holds nothing cheaper. ``shared`` names the goal
    cells another wire may hold — the tree cells this one attaches to.
    """
    if grid.native is not None:
        return grid.native.astar(
            layer,
            grid._code(wire_id),
            _ends(starts),
            _ends(goals),
            present_cost,
            share,
            limit,
            None if shared is None else [(c[0], c[1]) for c in shared],
        )
    return search(
        grid, layer, wire_id, starts, goals, present_cost, share, limit, shared
    )


def _ends(cells: dict[Cell, set[Edge] | None]) -> list[tuple[int, int, int]]:
    """Cells with a bitmask of the directions a path may leave or enter them by, 0 for any."""
    out = []
    for cell, edges in cells.items():
        mask = 0 if edges is None else sum(STEP_BIT[edge] for edge in edges)
        out.append((cell[0], cell[1], mask))
    return out


def search(
    grid: RouteGrid,
    layer: int,
    wire_id: str,
    starts: dict[Cell, set[Edge] | None],
    goals: dict[Cell, set[Edge] | None],
    present_cost: float,
    share: bool = True,
    limit: float = float("inf"),
    shared: set[Cell] | None = None,
) -> list[Cell] | None:
    """The search itself, in Python: what ``astar`` runs without the native grid."""
    if not starts or not goals:
        return None
    both = [c for c in starts if c in goals]
    if both:
        return [min(both)]
    gx0 = min(c[0] for c in goals)
    gx1 = max(c[0] for c in goals)
    gy0 = min(c[1] for c in goals)
    gy1 = max(c[1] for c in goals)
    width, height = grid.width, grid.height
    blocked = grid.blocked[layer]
    reserved = grid.reserved[layer]
    holders = grid.holders[layer]
    history = grid.history[layer]
    units = grid.units[layer]
    history_cost = grid.history_cost
    bridge_cost = grid.bridge_cost
    turn_cost = grid.turn_cost
    ground = layer == 0

    def heuristic(cell: Cell) -> int:
        x, y = cell
        dx = gx0 - x if x < gx0 else (x - gx1 if x > gx1 else 0)
        dy = gy0 - y if y < gy0 else (y - gy1 if y > gy1 else 0)
        return dx + dy

    frontier: list[tuple[float, int, Cell, Edge | None, bool]] = []
    best: dict[tuple[Cell, Edge | None], float] = {}
    parent: dict[tuple[Cell, Edge | None], tuple[Cell, Edge | None] | None] = {}
    counter = 0
    for start in starts:
        state = (start, None)
        best[state] = 0.0
        parent[state] = None
        heapq.heappush(frontier, (heuristic(start), counter, start, None, False))
        counter += 1
    while frontier:
        estimate, _, cell, direction, crossing = heapq.heappop(frontier)
        if estimate > limit:
            return None
        state = (cell, direction)
        cost_here = best[state]
        if cell in goals and direction is not None and not crossing:
            return _unwind(parent, state)
        leave = starts.get(cell) if direction is None else None
        for step_dir, dx, dy in STEPS:
            if crossing and step_dir is not direction:
                continue
            if leave is not None and step_dir not in leave:
                continue
            if direction is not None and step_dir is OPPOSITE[direction]:
                continue
            nx, ny = cell[0] + dx, cell[1] + dy
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            nxt = (nx, ny)
            if nxt in blocked:
                continue
            if ground and grid.pipe_unit(nxt):
                continue
            owners = reserved.get(nxt)
            foreign = owners is not None and wire_id not in owners
            move = 1.0 + history_cost * history.get(nxt, 0.0)
            next_crossing = False
            attaching = nxt in goals and (shared is None or nxt in shared)
            if attaching:
                if foreign:
                    continue
                enter = goals[nxt]
                if enter is not None and step_dir not in enter:
                    continue
            else:
                if nxt in goals:
                    enter = goals[nxt]
                    if enter is not None and step_dir not in enter:
                        continue
                held = holders.get(nxt)
                others = {k: v for k, v in held.items() if k != wire_id} if held else {}
                if foreign and not (others and all(o in owners for o in others)):
                    continue
                if others:
                    if nxt in units:
                        continue
                    if _crossing_ok(others, step_dir) and (
                        ground or grid.ground_free(nxt)
                    ):
                        move += bridge_cost
                        next_crossing = True
                    elif foreign or not share:
                        continue
                    else:
                        move += present_cost * (1.0 + history.get(nxt, 0.0))
            if direction is not None and step_dir is not direction:
                move += turn_cost
            candidate = cost_here + move
            next_state = (nxt, step_dir)
            if candidate < best.get(next_state, float("inf")):
                best[next_state] = candidate
                parent[next_state] = state
                heapq.heappush(
                    frontier,
                    (candidate + heuristic(nxt), counter, nxt, step_dir, next_crossing),
                )
                counter += 1
    return None


def _unwind(
    parent: dict[tuple[Cell, Edge | None], tuple[Cell, Edge | None] | None],
    state: tuple[Cell, Edge | None],
) -> list[Cell]:
    path: list[Cell] = []
    current: tuple[Cell, Edge | None] | None = state
    while current is not None:
        path.append(current[0])
        current = parent[current]
    path.reverse()
    return path
