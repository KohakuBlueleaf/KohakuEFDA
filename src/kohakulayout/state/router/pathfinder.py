"""A* on one layer over the kernel, from a set of cells to a set of cells, with the pack's crossing rules.

A state is a cell and the direction it was entered by; a crossing cell admits only the
straight continuation. Another net's wire is a crossing when the rule allows one and the
other wire runs straight through, shareable when the pack says so, and otherwise a wall
or, when ripping is allowed, a priced obstacle the caller must rip.
"""

import heapq
import json
from dataclasses import dataclass, field
from typing import Any

from kohakulayout._rust_bridge import rust_astar
from kohakulayout.ir import Footprint
from kohakulayout.ir.geometry import XY, footprint_cells
from kohakulayout.physics.protocol import Occupant
from kohakulayout.state.kernel import holder_kind
from kohakulayout.state.router.protocol import Costs
from kohakulayout.state.router.reservations import reservation_price

DIRS: tuple[XY, ...] = ((1, 0), (0, 1), (-1, 0), (0, -1))


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
    rules: str | None = None

    def __post_init__(self) -> None:
        self.width = self.world.fabric.width
        self.height = self.world.fabric.height
        owners = self.world.open_attach_owners().get(self.layer, {})
        self.shut = frozenset(
            xy for xy, net_id in owners.items() if net_id != self.net_id
        )

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


@dataclass
class Entry:
    cost: int
    crossing: str | None = None
    reuse: bool = False
    rip: str | None = None


def straight_through(
    world: Any, layer: str, other_net: str, xy: XY, direction: XY
) -> bool:
    """Whether the other net's wire runs through ``xy`` perpendicular to ``direction``."""
    wire = world.wires.get(other_net)
    if wire is None:
        return False
    cells: set[XY] = set()
    for segment in wire.segments:
        if segment.layer == layer:
            cells.update(segment.cells)
    px, py = direction[1], direction[0]
    x, y = xy
    across = (x + px, y + py) in cells and (x - px, y - py) in cells
    along = (x + direction[0], y + direction[1]) in cells or (
        x - direction[0],
        y - direction[1],
    ) in cells
    return across and not along


def entry(search: Search, xy: XY, direction: XY | None) -> Entry | None:
    """The cost of entering ``xy`` moving ``direction``, or None when the cell is closed."""
    world = search.world
    x, y = xy
    if (
        x < 0
        or y < 0
        or x >= search.width
        or y >= search.height
        or xy in search.walls
        or xy in search.shut
    ):
        return None
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
                and straight_through(world, search.layer, ref, xy, direction)
            ):
                result.crossing = ref
                result.cost += search.costs.crossing
                continue
            if search.allow_rip and ref not in search.protected:
                result.rip = ref
                result.cost += search.costs.ripup * (
                    1 + search.history.get((search.layer, xy), 0)
                )
                continue
            return None
    if unit_ref is not None:
        unit = world.units[unit_ref]
        if result.crossing is None:
            return None
        rule = world.physics.carriers.crossing(
            search.carrier, world.netlist.nets[result.crossing].carrier
        )
        if rule.mode != "unit" or rule.unit is None or unit.footprint != rule.unit.id:
            return None
        result.reuse = True
    elif result.crossing is not None:
        rule = world.physics.carriers.crossing(
            search.carrier, world.netlist.nets[result.crossing].carrier
        )
        if rule.mode == "unit" and (
            rule.unit is None
            or not _only_wires(holders)
            or not occluded_free(world, rule.unit, xy)
        ):
            return None
    return result


def occluded_free(world: Any, unit: Footprint, xy: XY) -> bool:
    """Whether the layers a unit at ``xy`` occludes are free there; its own layer holds the wires it crosses."""
    cells = footprint_cells(xy[0], xy[1], unit.width, unit.height, 0)
    if not all(world.in_grid(c) for c in cells):
        return False
    return all(world.kernel.free_for(layer, cells) for layer in unit.occludes)


def _only_wires(holders: tuple[str, ...]) -> bool:
    return all(holder_kind(h)[0] == "wire" for h in holders)


def rules_of(search: Search) -> dict[str, Any]:
    """The tables the native search reads: nets, sharing and crossing per net on the layer, units, reservations."""
    world = search.world
    mine = search.occupant(search.net_id, search.carrier)
    nets: dict[str, str] = {}
    share_with: dict[str, bool] = {}
    crossings: dict[str, tuple[str, str]] = {}
    shapes: dict[str, dict[str, Any]] = {}
    units: dict[str, str] = {}
    reservations: dict[str, int | None] = {}
    for holder in world.kernel.holders_on(search.layer):
        kind, ref = holder_kind(holder)
        if kind == "wire" and ref != search.net_id and ref in world.netlist.nets:
            other = world.netlist.nets[ref]
            nets[ref] = other.carrier
            share_with[ref] = bool(
                world.share.may_share(mine, search.occupant(ref, other.carrier))
            )
            if other.carrier not in crossings:
                rule = world.physics.carriers.crossing(search.carrier, other.carrier)
                unit = rule.unit
                crossings[other.carrier] = (rule.mode, unit.id if unit else "")
                if unit is not None:
                    shapes[unit.id] = {
                        "width": unit.width,
                        "height": unit.height,
                        "layers": list(unit.occludes),
                    }
        elif kind == "unit" and ref in world.units:
            units[ref] = world.units[ref].footprint
        elif kind == "reserve":
            reservations[ref] = reservation_price(
                world, ref, search.carrier, search.costs
            )
    return {
        "net": search.net_id,
        "carrier": search.carrier,
        "step": search.costs.step,
        "turn": search.costs.turn,
        "crossing": search.costs.crossing,
        "share": search.costs.share,
        "corridor": search.costs.corridor,
        "ripup": search.costs.ripup,
        "max_steps": search.costs.max_steps,
        "allow_rip": search.allow_rip,
        "protected": sorted(search.protected),
        "walls": sorted(search.walls),
        "shut": sorted(search.shut),
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
        "reservations": reservations,
    }


def find(
    search: Search,
    sources: frozenset[XY],
    targets: frozenset[XY],
    avoid: frozenset[XY] = frozenset(),
) -> Found | None:
    """The cheapest path from any source to any target, never stepping into ``avoid``; None within the step budget."""
    if not sources or not targets:
        return None
    grid = getattr(search.world.kernel, "_grid", None)
    if grid is not None:
        native = rust_astar(
            grid,
            search.layer,
            sorted(sources),
            sorted(targets),
            search.native_rules,
            sorted(avoid),
        )
        if native is not None:
            return _found_from(native)
    heuristic = _heuristic(targets)
    best: dict[tuple[XY, XY | None], int] = {}
    parent: dict[tuple[XY, XY | None], tuple[XY, XY | None] | None] = {}
    meta: dict[tuple[XY, XY | None], Entry] = {}
    heap: list[tuple[int, int, XY, XY | None]] = []
    counter = 0
    for cell in sorted(sources):
        state = (cell, None)
        best[state] = 0
        parent[state] = None
        heapq.heappush(heap, (heuristic(cell), counter, cell, None))
        counter += 1
    expansions = 0
    while heap:
        _, _, cell, direction = heapq.heappop(heap)
        state = (cell, direction)
        g = best[state]
        if cell in targets and direction is not None:
            return _reconstruct(state, parent, meta, g)
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
            nxt = (cell[0] + move[0], cell[1] + move[1])
            if nxt in sources or nxt in avoid:
                continue
            step = entry(search, nxt, move)
            if step is None:
                continue
            if step.crossing is not None and nxt in targets:
                continue
            cost = (
                g
                + step.cost
                + (
                    search.costs.turn
                    if direction is not None and move != direction
                    else 0
                )
            )
            nstate = (nxt, move)
            if cost < best.get(nstate, cost + 1):
                best[nstate] = cost
                parent[nstate] = state
                meta[nstate] = step
                heapq.heappush(heap, (cost + heuristic(nxt), counter, nxt, move))
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
    )


def _heuristic(targets: frozenset[XY]) -> Any:
    if len(targets) > 32:
        return lambda cell: 0
    goals = tuple(targets)
    return lambda cell: min(abs(cell[0] - gx) + abs(cell[1] - gy) for gx, gy in goals)


def _reconstruct(state: Any, parent: dict, meta: dict, cost: int) -> Found:
    cells: list[XY] = []
    crossings: list[tuple[XY, str, bool]] = []
    rips: set[str] = set()
    current = state
    while current is not None:
        cells.append(current[0])
        step = meta.get(current)
        if step is not None:
            if step.crossing is not None:
                crossings.append((current[0], step.crossing, step.reuse))
            if step.rip is not None:
                rips.add(step.rip)
        current = parent[current]
    cells.reverse()
    crossings.reverse()
    return Found(
        cells=tuple(cells), cost=cost, crossings=tuple(crossings), rips=frozenset(rips)
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
