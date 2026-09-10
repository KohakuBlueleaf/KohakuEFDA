"""A* on one layer over the kernel, from a set of cells to a set of cells, with the pack's crossing rules.

A state is a cell and the direction it was entered by; a crossing cell admits only the
straight continuation. A path may start or end on a crossing: a terminal cell another
wire runs straight through is left, or reached, across that wire. Another net's wire is a crossing when the rule allows one and the
other wire runs straight through, shareable when the pack says so, and otherwise a wall
or, when ripping is allowed, a priced obstacle the caller must rip.
"""

import heapq
import json
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from kohakulayout._rust_bridge import rust_astar
from kohakulayout.ir.geometry import XY
from kohakulayout.physics.protocol import Occupant
from kohakulayout.state.crossing import occluded_free, only_wires, straight_through
from kohakulayout.state.kernel import holder_kind
from kohakulayout.state.router.protocol import Costs
from kohakulayout.state.router.reservations import reservation_price

DIRS: tuple[XY, ...] = ((0, -1), (1, 0), (0, 1), (-1, 0))


@dataclass
class Search:
    """One search's view of the world: what it routes, where it may go, what it may rip."""

    world: Any
    net_id: str
    carrier: str
    layer: str
    costs: Costs
    walls: frozenset[XY]
    history: dict[tuple[str, XY], int]
    allow_rip: bool = False
    protected: frozenset[str] = frozenset()
    occupants: dict[str, Occupant] = field(default_factory=dict)
    width: int = 0
    height: int = 0
    grid: dict[XY, tuple[str, ...]] | None = None
    shut: frozenset[XY] = frozenset()
    held: frozenset[XY] = frozenset()
    ports: dict[XY, XY] = field(default_factory=dict)
    rules: str | None = None
    walls_key: str = ""
    own: dict[XY, int] = field(default_factory=dict)
    end_on_crossing: bool = True
    float_scale: int = 0

    def __post_init__(self) -> None:
        self.width = self.world.fabric.width
        self.height = self.world.fabric.height
        self.walls_key = f"{self.carrier}@{id(self.world.fabric)}:{len(self.walls)}"
        owners = self.world.open_attach_owners().get(self.layer, {})
        self.shut = frozenset(
            xy for xy, net_id in owners.items() if net_id != self.net_id
        )
        routed = self.world.routed_attach_owners().get(self.layer, {})
        self.held = frozenset(
            xy for xy, net_id in routed.items() if net_id != self.net_id
        )
        ports = self.world.routed_attach_ports().get(self.layer, {})
        self.ports = {
            xy: port for xy, port in ports.items() if routed.get(xy) != self.net_id
        }

    def holders(self, xy: XY) -> tuple[str, ...] | None:
        """The holders at ``xy`` on this layer, from a snapshot taken on first use."""
        if self.grid is None:
            self.grid = self.world.kernel.holders_map(self.layer)
        return self.grid.get(xy)

    def native_rules(self) -> str:
        """The search as JSON tables for the native twin: every pack answer the search may ask, asked once."""
        if self.rules is None:
            self.rules = json.dumps(rules_of(self))
        return self.rules

    def occupant(self, net_id: str, carrier: str) -> Occupant:
        found = self.occupants.get(net_id)
        if found is None:
            found = self.occupants[net_id] = Occupant(
                kind="wire", carrier=carrier, id=net_id
            )
        return found


@dataclass
class Found:
    cells: tuple[XY, ...]
    cost: int
    crossings: tuple[tuple[XY, str, bool], ...]
    rips: frozenset[str]
    displaces: frozenset[str] = frozenset()


@dataclass
class Entry:
    cost: int
    crossing: str | None = None
    reuse: bool = False
    rips: frozenset[str] = frozenset()
    displaces: frozenset[str] = frozenset()


def own_crossing(search: Search, xy: XY, direction: XY | None) -> Entry | None:
    """The cost of crossing one of the net's own standing lanes at ``xy``: across its run only, with the carrier's own crossing unit where the pack needs one; None when the move runs along it or no crossing may stand."""
    if direction is None:
        return None
    along = direction[1] == 0 if search.own[xy] == 1 else direction[0] == 0
    if along:
        return None
    rule = search.world.physics.carriers.crossing(search.carrier, search.carrier)
    if rule.mode == "forbidden":
        return None
    if rule.mode == "unit" and (
        rule.unit is None or not occluded_free(search.world, rule.unit, xy)
    ):
        return None
    return Entry(cost=search.costs.step + search.costs.crossing, crossing=search.net_id)


def entry(
    search: Search, xy: XY, direction: XY | None, terminal: bool = False
) -> Entry | None:
    """The cost of entering ``xy`` moving ``direction``, or None when the cell is closed; a ``terminal`` is the path's own start, where only what holds the cell matters and a bent crossing, when the pack allows one, may stand; a cell of the net's own standing lanes (``own``) is crossed, at either end or on the way. A field emitter on the cell is displaced, the cover redone when the plan commits."""
    world = search.world
    x, y = xy
    if x < 0 or y < 0 or x >= search.width or y >= search.height:
        return None
    if not terminal and (xy in search.walls or xy in search.shut):
        return None
    if xy in search.own:
        return own_crossing(search, xy, direction)
    holders = search.holders(xy)
    if holders is None:
        return Entry(cost=search.costs.step)
    result = Entry(cost=search.costs.step)
    mine = search.occupant(search.net_id, search.carrier)
    unit_ref: str | None = None
    for holder in holders:
        kind, ref = holder_kind(holder)
        if kind == "cell":
            return None
        if kind == "reserve":
            price = reservation_price(world, ref, search.carrier, search.costs)
            if price is None:
                return None
            result.cost += price
        elif kind == "unit":
            unit_ref = ref
        elif kind == "wire":
            if ref == search.net_id:
                return None
            other = world.netlist.nets[ref]
            if world.share.may_share(mine, search.occupant(ref, other.carrier)):
                result.cost += search.costs.share
                continue
            rule = world.physics.carriers.crossing(search.carrier, other.carrier)
            if (
                rule.mode != "forbidden"
                and direction is not None
                and straight_through(
                    world,
                    search.layer,
                    ref,
                    xy,
                    direction,
                    search.ports.get(xy),
                    rule.bent and terminal,
                )
            ):
                result.crossing = ref
                result.cost += search.costs.crossing
                continue
            if (
                search.allow_rip
                and ref not in search.protected
                and xy not in search.held
            ):
                result.rips = result.rips | {ref}
                result.cost += search.costs.ripup * (
                    1 + search.history.get((search.layer, xy), 0)
                )
                continue
            return None
    if unit_ref is not None and world.units[unit_ref].owner.startswith("field:"):
        result.displaces = frozenset({unit_ref})
        result.cost += search.costs.displace
        holders = tuple(h for h in holders if h != f"unit:{unit_ref}")
        unit_ref = None
    if unit_ref is not None:
        unit = world.units[unit_ref]
        owner = unit.owner.removeprefix("net:")
        if result.crossing is not None:
            rule = world.physics.carriers.crossing(
                search.carrier, world.netlist.nets[result.crossing].carrier
            )
            if (
                rule.mode != "unit"
                or rule.unit is None
                or unit.footprint != rule.unit.id
            ):
                return None
            result.reuse = True
        elif owner in result.rips:
            pass
        elif (
            owner in world.netlist.nets
            and search.allow_rip
            and owner not in search.protected
            and xy not in search.held
        ):
            result.rips = result.rips | {owner}
            result.cost += search.costs.ripup * (
                1 + search.history.get((search.layer, xy), 0)
            )
        else:
            return None
    elif result.crossing is not None:
        rule = world.physics.carriers.crossing(
            search.carrier, world.netlist.nets[result.crossing].carrier
        )
        if rule.mode == "unit" and (
            rule.unit is None
            or not only_wires(holders)
            or not occluded_free(
                world, rule.unit, xy, frozenset(f"unit:{u}" for u in result.displaces)
            )
        ):
            return None
    return result


_UNIT_TABLES: dict[tuple[int, str], tuple[int, tuple[dict, dict, dict]]] = {}


def _unit_tables(world: Any, layer: str) -> tuple[dict, dict, dict]:
    """The units on a layer with their footprints, owners and field flags, rebuilt when a unit comes or goes."""
    key = (id(world), layer)
    hit = _UNIT_TABLES.get(key)
    if hit is not None and hit[0] == world.units_rev:
        return hit[1]
    units: dict[str, str] = {}
    unit_owners: dict[str, str] = {}
    unit_fields: dict[str, bool] = {}
    for ref, unit in world.units.items():
        if layer in world.layers_for(world.library[unit.footprint]):
            units[ref] = unit.footprint
            unit_owners[ref] = unit.owner.removeprefix("net:")
            if unit.owner.startswith("field:"):
                unit_fields[ref] = True
    tables = (units, unit_owners, unit_fields)
    _UNIT_TABLES[key] = (world.units_rev, tables)
    return tables


def rules_of(search: Search) -> dict[str, Any]:
    """The tables the native search reads: nets, sharing and crossing per net on the layer, units, reservations."""
    world = search.world
    mine = search.occupant(search.net_id, search.carrier)
    nets: dict[str, str] = {}
    share_with: dict[str, bool] = {}
    crossings: dict[str, tuple[str, str]] = {}
    shapes: dict[str, dict[str, Any]] = {}
    units, unit_owners, unit_fields = _unit_tables(world, search.layer)
    reservations: dict[str, int | None] = {}
    nets[search.net_id] = search.carrier
    own_rule = world.physics.carriers.crossing(search.carrier, search.carrier)
    crossings[search.carrier] = (
        own_rule.mode,
        own_rule.unit.id if own_rule.unit else "",
        own_rule.bent,
    )
    if own_rule.unit is not None:
        shapes[own_rule.unit.id] = {
            "width": own_rule.unit.width,
            "height": own_rule.unit.height,
            "layers": list(own_rule.unit.occludes),
        }
    for ref, wire in world.wires.items():
        if ref == search.net_id or ref not in world.netlist.nets:
            continue
        if all(segment.layer != search.layer for segment in wire.segments):
            continue
        other = world.netlist.nets[ref]
        nets[ref] = other.carrier
        share_with[ref] = bool(
            world.share.may_share(mine, search.occupant(ref, other.carrier))
        )
        if other.carrier not in crossings:
            rule = world.physics.carriers.crossing(search.carrier, other.carrier)
            unit = rule.unit
            crossings[other.carrier] = (rule.mode, unit.id if unit else "", rule.bent)
            if unit is not None:
                shapes[unit.id] = {
                    "width": unit.width,
                    "height": unit.height,
                    "layers": list(unit.occludes),
                }
    for ref, reservation in world.reservations.items():
        if reservation.layer == search.layer:
            reservations[ref] = reservation_price(
                world, ref, search.carrier, search.costs
            )
    return {
        "net": search.net_id,
        "carrier": search.carrier,
        "step": search.costs.step,
        "turn": search.costs.turn,
        "crossing": search.costs.crossing,
        "displace": search.costs.displace,
        "share": search.costs.share,
        "corridor": search.costs.corridor,
        "ripup": search.costs.ripup,
        "max_steps": search.costs.max_steps,
        "detour": search.costs.detour,
        "slack": search.costs.slack,
        "allow_rip": search.allow_rip,
        "end_on_crossing": search.end_on_crossing,
        "float_scale": search.float_scale,
        "protected": sorted(search.protected),
        "walls": [],
        "walls_key": search.walls_key,
        "shut": sorted(search.shut),
        "held": sorted(search.held),
        "ports": sorted((a[0], a[1], p[0], p[1]) for a, p in search.ports.items()),
        "history": [
            (xy[0], xy[1], n)
            for (layer, xy), n in search.history.items()
            if layer == search.layer
        ],
        "nets": nets,
        "share_with": share_with,
        "crossings": crossings,
        "shapes": shapes,
        "units": units,
        "unit_owners": unit_owners,
        "unit_fields": unit_fields,
        "all_nets": sorted(world.netlist.nets),
        "reservations": reservations,
    }


def register_walls(grid: Any, search: Search) -> None:
    """Hand the search's walls to the native grid once per key, so the rules carry only the key."""
    if hasattr(grid, "has_walls") and not grid.has_walls(search.walls_key):
        grid.set_walls(search.walls_key, sorted(search.walls))


def cost_limit(
    search: Search, sources: frozenset[XY], targets: frozenset[XY]
) -> float | None:
    """What a path may cost before it is not worth having: the shortest span across stretched by ``detour`` plus ``slack``; None when the costs set no detour."""
    if search.costs.detour <= 0:
        return None
    span = min(abs(a[0] - b[0]) + abs(a[1] - b[1]) for a in sources for b in targets)
    return search.costs.slack + search.costs.detour * span


def find(
    search: Search,
    sources: frozenset[XY],
    targets: frozenset[XY],
    avoid: frozenset[XY] = frozenset(),
    order: tuple[XY, ...] = (),
) -> Found | None:
    """The cheapest path from any source to any target, never stepping into ``avoid``; None within the step budget. Among paths of one cost the first found wins, so ``order`` says which sources the search opens first (the rest after, sorted)."""
    if not sources or not targets:
        return None
    starts_in = [c for c in order if c in sources]
    starts_in += sorted(sources - set(starts_in))
    grid = getattr(search.world.kernel, "_grid", None)
    if grid is not None:
        register_walls(grid, search)
        native = rust_astar(
            grid,
            search.layer,
            starts_in,
            sorted(targets),
            search.native_rules,
            sorted(avoid),
            sorted((x, y, axis) for (x, y), axis in search.own.items()),
        )
        if native is not None:
            return _found_from(native)
    heuristic = _heuristic(targets, search.costs.step)
    limit = cost_limit(search, sources, targets)
    scale = search.float_scale
    floats = scale > 0
    f32 = np.float32

    def as_f(value: int) -> Any:
        return f32(value) / f32(scale)

    best: dict[tuple[XY, XY | None], Any] = {}
    parent: dict[tuple[XY, XY | None], tuple[XY, XY | None] | None] = {}
    meta: dict[tuple[XY, XY | None], Entry] = {}
    starts: dict[tuple[XY, XY | None], Entry] = {}
    heap: list[tuple[Any, int, XY, XY | None]] = []
    counter = 0
    for cell in starts_in:
        state = (cell, None)
        best[state] = f32(0) if floats else 0
        parent[state] = None
        h = heuristic(cell)
        heapq.heappush(heap, (as_f(h) if floats else h, counter, cell, None))
        counter += 1
    expansions = 0
    while heap:
        estimate, _, cell, direction = heapq.heappop(heap)
        if limit is not None and (estimate > (f32(limit / scale) if floats else limit)):
            return None
        state = (cell, direction)
        g = best[state]
        if cell in targets and direction is not None:
            here = meta.get(state)
            if search.end_on_crossing or here is None or here.crossing is None:
                total = round(float(g) * scale) if floats else g
                return _reconstruct(state, parent, meta, starts, total)
            continue
        expansions += 1
        if expansions > search.costs.max_steps:
            return None
        here = meta.get(state)
        moves = (
            (direction,)
            if here is not None and here.crossing is not None and direction is not None
            else DIRS
        )
        for move in moves:
            if direction is not None and move == (-direction[0], -direction[1]):
                continue
            nxt = (cell[0] + move[0], cell[1] + move[1])
            if nxt in sources or nxt in avoid:
                continue
            start = (
                entry(search, cell, move, terminal=True) if direction is None else None
            )
            if direction is None and start is None:
                continue
            step = entry(search, nxt, move)
            if step is None:
                continue
            if floats:
                move_cost = as_f(step.cost)
                if direction is not None and move != direction:
                    move_cost += as_f(search.costs.turn)
                cost = g + move_cost
            else:
                cost = g + step.cost
                if direction is not None and move != direction:
                    cost += search.costs.turn
                if start is not None:
                    cost += start.cost - search.costs.step
            nstate = (nxt, move)
            if nstate not in best or cost < best[nstate]:
                best[nstate] = cost
                parent[nstate] = state
                meta[nstate] = step
                if start is not None and (
                    start.crossing is not None or start.rips or start.displaces
                ):
                    starts[nstate] = start
                else:
                    starts.pop(nstate, None)
                h = heuristic(nxt)
                heapq.heappush(
                    heap, (cost + (as_f(h) if floats else h), counter, nxt, move)
                )
                counter += 1
    return None


def _found_from(answer: str) -> Found | None:
    """The native answer: the JSON of a path, or the word ``none`` when there is none."""
    if answer == "none":
        return None
    raw = json.loads(answer)
    return Found(
        cells=tuple((x, y) for x, y in raw["cells"]),
        cost=raw["cost"],
        crossings=tuple(
            ((x, y), net, reuse) for (x, y), net, reuse in raw["crossings"]
        ),
        rips=frozenset(raw["rips"]),
        displaces=frozenset(raw.get("displaces", ())),
    )


def _heuristic(targets: frozenset[XY], step: int) -> Any:
    """The Manhattan span to the targets' bounding box in step costs: never more than the way to the nearest target, and the same for any count of them."""
    x0 = min(x for x, _ in targets)
    x1 = max(x for x, _ in targets)
    y0 = min(y for _, y in targets)
    y1 = max(y for _, y in targets)

    def estimate(cell: XY) -> int:
        x, y = cell
        dx = x0 - x if x < x0 else (x - x1 if x > x1 else 0)
        dy = y0 - y if y < y0 else (y - y1 if y > y1 else 0)
        return step * (dx + dy)

    return estimate


def _reconstruct(
    state: Any, parent: dict, meta: dict, starts: dict, cost: int
) -> Found:
    """The path back from a target: its cells, the crossings and rips its steps recorded, and the start cell's own."""
    cells: list[XY] = []
    crossings: list[tuple[XY, str, bool]] = []
    rips: set[str] = set()
    displaces: set[str] = set()
    current = state
    while current is not None:
        cells.append(current[0])
        step = meta.get(current)
        if step is not None:
            if step.crossing is not None:
                crossings.append((current[0], step.crossing, step.reuse))
            rips.update(step.rips)
            displaces.update(step.displaces)
        start = starts.get(current)
        previous = parent[current]
        if start is not None and previous is not None:
            if start.crossing is not None:
                crossings.append((previous[0], start.crossing, start.reuse))
            rips.update(start.rips)
            displaces.update(start.displaces)
        current = previous
    cells.reverse()
    crossings.reverse()
    return Found(
        cells=tuple(cells),
        cost=cost,
        crossings=tuple(crossings),
        rips=frozenset(rips),
        displaces=frozenset(displaces),
    )


__all__ = [
    "DIRS",
    "Found",
    "Search",
    "entry",
    "find",
    "occluded_free",
    "rules_of",
    "straight_through",
]
