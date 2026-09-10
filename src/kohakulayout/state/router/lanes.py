"""Lanes: a net as a bundle of pin-to-pin lanes, each laid from its source pin's own lanes to its sink pin's.

A lane runs from one source pin to one sink pin. It starts on a straight cell of the
lanes its source pin already has, or on one of the pin's open attach cells when it has
none, and ends on a straight cell of the lanes into its sink pin, or on one of that
pin's open attach cells; two pins with no lane yet are joined port to port, apart from
whatever else the net has laid. The only attach cell of a pin with one port is that
pin's alone: no other lane of the net runs through it or attaches there. A lane that leaves another makes a split where it
leaves, a lane that ends on another a merge where it ends. Every lane whose two pins
are placed is laid, in the policy's order, and the first without a path refuses the net.
"""

import logging
from typing import Any

from kohakulayout.ir import PinRef, Refusal, Segment
from kohakulayout.ir.geometry import XY
from kohakulayout.state.router.default import DefaultRouter
from kohakulayout.state.router.pathfinder import Search, find
from kohakulayout.state.router.protocol import Terminal, refuse, register, terminals
from kohakulayout.state.router.trees import (
    DEFAULT_POLICY,
    Plan,
    Seed,
    TreePolicy,
    grow,
    may_join,
    seed_of,
    single_cell,
)

Pins = tuple[PinRef | None, PinRef | None]
log = logging.getLogger(__name__)


def attach_pins(found: tuple[Terminal, ...], ports: dict[str, str]) -> dict[XY, PinRef]:
    """The pin behind each attach cell a standing lane may end on: a bound pin's only cell, a recorded port's cell, every option of a pin with none recorded; a bound or recorded pin outranks a sibling's option on the same cell."""
    at: dict[XY, PinRef] = {}
    for terminal in found:
        if not terminal.bound and str(terminal.ref) not in ports:
            for _, attach in terminal.options:
                at[attach] = terminal.ref
    for terminal in found:
        recorded = ports.get(str(terminal.ref))
        for port, attach in terminal.options:
            if terminal.bound or port == recorded:
                at[attach] = terminal.ref
    return at


def lane_pins(
    segments: list[Segment], at: dict[XY, PinRef], sources: frozenset[PinRef]
) -> list[Pins]:
    """The source and sink pin of every standing segment, read from its ends: a head on a source's attach cell is that source, a tail on a sink's that sink, and an end on another segment takes that segment's pin on the same side, until nothing changes."""
    runs = [list(seg.cells) for seg in segments]
    pins: list[list[PinRef | None]] = []
    for run in runs:
        head, tail = at.get(run[0]), at.get(run[-1])
        pins.append(
            [
                head if head is not None and head in sources else None,
                tail if tail is not None and tail not in sources else None,
            ]
        )
    changed = True
    while changed:
        changed = False
        for i, run in enumerate(runs):
            for side, end in ((0, run[0]), (1, run[-1])):
                if pins[i][side] is not None:
                    continue
                for j, other in enumerate(runs):
                    if j != i and end in other and pins[j][side] is not None:
                        pins[i][side] = pins[j][side]
                        changed = True
                        break
    return [(a, b) for a, b in pins]


def crossable_own(
    world: Any,
    search: Search,
    segments: list[Segment],
    junctions: dict[XY, str],
    crossed: set[XY],
    behind: dict[XY, XY] | None = None,
) -> dict[XY, int]:
    """The cells of the net's standing lanes another of its lanes may cross, with the axis the lane runs along there (1 across, 2 down): a cell inside a run, straight, no junction or crossing, held by nothing else; a run's end cell counts when the port cell ``behind`` it lines up."""
    out: dict[XY, int] = {}
    for segment in segments:
        cells = list(segment.cells)
        if behind:
            if cells[0] in behind:
                cells = [behind[cells[0]], *cells]
            if cells[-1] in behind:
                cells = [*cells, behind[cells[-1]]]
        for i in range(1, len(cells) - 1):
            before, here, after = cells[i - 1], cells[i], cells[i + 1]
            if before[0] == after[0]:
                axis = 2
            elif before[1] == after[1]:
                axis = 1
            else:
                continue
            if here in junctions or here in crossed or here in out:
                out.pop(here, None)
                continue
            if world.kernel.holders_at(search.layer, here):
                continue
            out[here] = axis
    return out


def whole_lanes(
    segments: list[Segment], at: dict[XY, PinRef], sources: frozenset[PinRef]
) -> tuple[list[Segment], list[Pins]]:
    """The standing segments that still read as whole lanes, with their pins: a segment with an end no pin or lane accounts for (a lane a placement cut) is dropped and its lane laid again, and what read through it is dropped with it."""
    kept = list(segments)
    while kept:
        read = lane_pins(kept, at, sources)
        whole = [
            seg for seg, (s, t) in zip(kept, read) if s is not None and t is not None
        ]
        if len(whole) == len(kept):
            return kept, read
        kept = whole
    return [], []


def standing_lanes(world: Any, net: Any, seed: Seed | None) -> set[tuple[Any, Any]]:
    """The lanes the net's standing wire carries whole, read from the seed."""
    if seed is None or not seed.segments:
        return set()
    found = terminals(world, net)
    if isinstance(found, Refusal):
        return set()
    _, read = whole_lanes(
        seed.segments, attach_pins(found, seed.ports), frozenset(net.sources)
    )
    return set(read)


def lay(
    world: Any,
    net: Any,
    search: Search,
    seed: Seed | None = None,
    policy: TreePolicy = DEFAULT_POLICY,
    only: tuple[Any, Any] | None = None,
) -> Plan | Refusal:
    """A plan laying every lane of ``net`` whose two pins are placed and that the standing wire does not carry yet, in the policy's order, or ``only`` the one named; a net with an outside edge grows as a tree."""
    found = terminals(world, net)
    if isinstance(found, Refusal):
        return found
    if world.physics.boundaries.outside(world, net):
        return grow(world, net, search, seed, policy)
    rule = world.physics.carriers.junction(net.carrier)
    by_ref = {str(t.ref): t for t in found}
    port_at = {(str(t.ref), attach): port for t in found for port, attach in t.options}
    sources = frozenset(net.sources)
    plan = Plan(net_id=net.id)
    pins: list[Pins] = plan.lanes
    junction_at: dict[XY, str] = {}
    sat: dict[XY, set[str]] = {}
    seated: dict[str, XY] = {}

    def took(terminal: Terminal, cell: XY) -> None:
        sat.setdefault(cell, set()).add(terminal.ref.cell)
        seated[str(terminal.ref)] = cell
        if not terminal.bound:
            plan.ports[str(terminal.ref)] = port_at[(str(terminal.ref), cell)]

    at = attach_pins(found, seed.ports if seed is not None else {})
    behind: dict[XY, XY] = {}
    for terminal in found:
        recorded = (seed.ports if seed is not None else {}).get(str(terminal.ref))
        for port, attach, port_cell in world.port_choices(terminal.ref.cell).get(
            terminal.ref.pin, ()
        ):
            if terminal.bound or port == recorded:
                behind[attach] = port_cell
    seed_crossings = list(seed.crossings) if seed is not None else []
    seed_junctions = dict(seed.junctions) if seed is not None else {}
    crossed: set[XY] = set()

    def absorb(segments: list[Segment]) -> None:
        """Start the plan again from these standing segments: those still whole lanes, with the crossings, ports and seats they carry and the junctions their own ends make on one another (a dropped lane's split or merge goes with it)."""
        kept, read = whole_lanes(segments, at, sources)
        cells = {c for seg in kept for c in seg.cells}
        plan.segments[:] = kept
        pins[:] = read
        plan.crossings[:] = [c for c in seed_crossings if c[0] in cells]
        plan.ports.clear()
        plan.ports.update(seed.ports if seed is not None else {})
        junction_at.clear()
        for i, segment in enumerate(kept):
            others = {c for j, other in enumerate(kept) if j != i for c in other.cells}
            head, tail = segment.cells[0], segment.cells[-1]
            if head in others and seed_junctions.get(head) == "split":
                junction_at[head] = "split"
            if tail in others and seed_junctions.get(tail) == "merge":
                junction_at[tail] = "merge"
        sat.clear()
        seated.clear()
        for segment, (source, sink) in zip(kept, read):
            for ref, cell in ((source, segment.cells[0]), (sink, segment.cells[-1])):
                terminal = by_ref.get(str(ref)) if ref is not None else None
                if terminal is not None and any(a == cell for _, a in terminal.options):
                    took(terminal, cell)
        crossed.clear()
        crossed.update(xy for xy, _, _ in plan.crossings)

    if seed is not None and seed.segments:
        absorb(list(seed.segments))
    standing: dict[XY, bool] = {}

    def stands(cell: XY) -> bool:
        if cell in crossed or cell in junction_at:
            return False
        found_here = standing.get(cell)
        if found_here is None:
            found_here = standing[cell] = may_join(world, rule, cell, search.layer)
        return found_here

    def tree_of(ref: PinRef, side: int) -> list[int]:
        return [i for i, pair in enumerate(pins) if pair[side] == ref]

    def open_for(terminal: Terminal) -> tuple[XY, ...]:
        return tuple(
            attach
            for _, attach in terminal.options
            if terminal.ref.cell not in sat.get(attach, ())
        )

    def ends(terminal: Terminal, side: int) -> tuple[tuple[XY, ...], frozenset[XY]]:
        """Where a lane may start (side 0) or end (side 1) at this pin, in the order a search opens them: the straight cells of its own lanes the policy allows, lane by lane along each run, else its open attach cells in the pin's port order, one another lane of the net runs straight through crossed there; with the cells of those lanes."""
        mine = tree_of(terminal.ref, side)
        if not mine:
            held = frozenset(c for seg in plan.segments for c in seg.cells)
            crossable = crossable_own(
                world, search, plan.segments, junction_at, crossed, behind
            )
            shut = held - frozenset(crossable)
            return tuple(c for c in open_for(terminal) if c not in shut), frozenset()
        own = Plan(net_id=net.id, segments=[plan.segments[i] for i in mine])
        own.ports = plan.ports
        own.lanes = [pins[i] for i in mine]
        cells = frozenset(c for seg in own.segments for c in seg.cells)
        joinable = frozenset(c for c in cells if stands(c))
        allowed = policy.origins(world, net, own, junction_at, joinable, side == 1)
        ordered = tuple(
            dict.fromkeys(c for seg in own.segments for c in seg.cells if c in allowed)
        )
        if log.isEnabledFor(logging.DEBUG):
            log.debug(
                "ends of %s side %d: runs=%s joinable=%s allowed=%s ports=%s",
                terminal.ref,
                side,
                [list(seg.cells) for seg in own.segments],
                sorted(joinable),
                sorted(allowed),
                own.ports,
            )
            log.debug(
                "not joinable: %s",
                [
                    (c, c in crossed, c in junction_at, standing.get(c))
                    for c in sorted(cells - joinable)
                ],
            )
        return ordered, cells

    queue = list(policy.lanes(world, net))
    again: set[tuple[Any, Any]] = set()
    forced: set[tuple[Any, Any]] = set()
    position = 0
    while position < len(queue):
        source, sink = queue[position]
        position += 1
        if (source, sink) in pins:
            continue
        if only is not None and (source, sink) != only and (source, sink) not in again:
            continue
        a, b = by_ref.get(str(source)), by_ref.get(str(sink))
        if a is None or b is None:
            continue
        first, source_tree = ends(a, 0)
        goals_in, sink_tree = ends(b, 1)
        starts, goals = frozenset(first), frozenset(goals_in)
        if (not starts or not goals) and (source, sink) not in forced:
            forced.add((source, sink))
            victims = [
                pair
                for pair in policy.blockers(world, net, plan, source, sink)
                if pair in pins
            ]
            if victims:
                absorb(
                    [
                        seg
                        for seg, pair in zip(plan.segments, pins)
                        if pair not in victims
                    ]
                )
                gone = [pair for pair in queue[: position - 1] if pair not in pins]
                again.update(gone)
                queue[position:position] = [
                    pair for pair in gone if pair not in queue[position:]
                ]
                position -= 1
                continue
        if not starts or not goals:
            side = "start from" if not starts else "end on"
            log.debug(
                "lane %s>%s has no cell to %s: starts=%s goals=%s sat=%s source_tree=%s sink_tree=%s",
                source,
                sink,
                side,
                sorted(starts),
                sorted(goals),
                {k: sorted(v) for k, v in sat.items()},
                sorted(source_tree),
                sorted(sink_tree),
            )
            return refuse(net.id, f"lane {source}>{sink} has no cell to {side}")
        tree_cells = frozenset(c for seg in plan.segments for c in seg.cells)
        reserved = frozenset(
            t.options[0][1] for t in found if t.bound and t not in (a, b)
        )
        starts, goals = starts - reserved, goals - reserved
        if not starts or not goals:
            return refuse(net.id, f"lane {source}>{sink} has only reserved cells")
        own = crossable_own(world, search, plan.segments, junction_at, crossed, behind)
        search.own = {
            c: axis for c, axis in own.items() if c not in source_tree | sink_tree
        }
        if log.isEnabledFor(logging.DEBUG):
            log.debug(
                "lane %s>%s starts=%s goals=%s source_tree=%s sink_tree=%s sat=%s junctions=%s crossed=%s own=%s",
                source,
                sink,
                sorted(starts),
                sorted(goals),
                sorted(source_tree),
                sorted(sink_tree),
                {k: sorted(v) for k, v in sat.items()},
                junction_at,
                sorted(crossed),
                sorted(search.own),
            )
        both = starts & goals
        if both:
            only = single_cell(world, net, search, a, both, plan)
            if only is None:
                return refuse(net.id, f"lane {source}>{sink}: its only cell is held")
            if not policy.single_cell_lane(
                world, net, source, sink, only in source_tree, only in sink_tree
            ):
                return refuse(net.id, f"lane {source}>{sink} would be one cell")
            cells: tuple[XY, ...] = (only,)
        else:
            avoid = tree_cells - starts - goals - frozenset(search.own)
            path = find(search, starts, goals, avoid | reserved, first)
            if path is None:
                return refuse(
                    net.id,
                    f"no path for lane {source}>{sink} from {min(starts)} to any of "
                    f"{sorted(goals)[:4]}",
                )
            cells = path.cells
            plan.crossings.extend(path.crossings)
            crossed.update(xy for xy, _, _ in path.crossings)
            plan.rips |= path.rips
            plan.displaced |= path.displaces
            plan.cost += path.cost
        head, tail = cells[0], cells[-1]
        if head in source_tree:
            junction_at[head] = "split"
        else:
            took(a, head)
        if tail in sink_tree:
            junction_at[tail] = "merge"
        else:
            took(b, tail)
        crossed.update(xy for xy, _, _ in plan.crossings)
        plan.segments.append(
            Segment(carrier=net.carrier, layer=search.layer, cells=tuple(cells))
        )
        pins.append((source, sink))
        log.debug("laid lane %s>%s cells=%s", source, sink, list(cells))
    plan.junctions = list(junction_at.items())
    return plan


@register
class LaneRouter(DefaultRouter):
    """The default router laying a net as a bundle of lanes; the policy's ``lanes`` names them in order and its ``rank`` orders the lanes of the nets one placement touches, laid one at a time across nets."""

    id = "lanes"

    def __init__(self, *args: Any, float_scale: int = 0, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.only: tuple[Any, Any] | None = None
        self.float_scale = float_scale

    def plan(self, world: Any, net: Any, search: Search, seed: Any) -> Plan | Refusal:
        return lay(world, net, search, seed, self.policy, self.only)

    def search(self, *args: Any, **kwargs: Any) -> Search:
        """The default search with ``end_on_crossing`` off and the router's ``float_scale``."""
        made = super().search(*args, **kwargs)
        made.end_on_crossing = False
        made.float_scale = self.float_scale
        return made

    def route(self, world: Any, net_id: str) -> Refusal | None:
        """Lay the net's ready lanes; a net with no wire and no lane whose two pins are placed is left for a later placement."""
        net = world.netlist.nets[net_id]
        if net_id not in world.wires and not any(
            s.cell in world.placements and t.cell in world.placements
            for s, t in self.policy.lanes(world, net)
        ):
            return None
        return super().route(world, net_id)

    def route_all(
        self, world: Any, cell_id: str, pending: list[str], grown: set[str]
    ) -> Refusal | None:
        """Lay every lane the placement made ready, across the nets it touches, in the policy's rank: the nets in the router's order break ties, then the policy's lane order within a net; the first lane without a path refuses."""
        ordered = self.order(world, cell_id, pending, grown)
        queue: list[tuple[Any, int, int, str, Any, Any]] = []
        for position, net_id in enumerate(ordered):
            net = world.netlist.nets[net_id]
            standing = standing_lanes(world, net, seed_of(world, net))
            for index, (source, sink) in enumerate(self.policy.lanes(world, net)):
                if (source, sink) in standing:
                    standing.discard((source, sink))
                    continue
                if (
                    source.cell not in world.placements
                    or sink.cell not in world.placements
                ):
                    continue
                rank = self.policy.rank(world, net, source, sink)
                queue.append((rank, position, index, net_id, source, sink))
        queue.sort(key=lambda item: item[:3])
        try:
            for _, _, _, net_id, source, sink in queue:
                self.only = (source, sink)
                refusal = world.route(net_id, grow=net_id in world.wires)
                if refusal is not None:
                    return refusal
        finally:
            self.only = None
        return None

    def cost(self, world: Any, net_id: str) -> int | None:
        net = world.netlist.nets[net_id]
        seed = seed_of(world, net)
        plan = lay(
            world, net, self.search(world, net, False, frozenset({net_id})), seed
        )
        return None if isinstance(plan, Refusal) else plan.cost


__all__ = [
    "LaneRouter",
    "attach_pins",
    "lane_pins",
    "lay",
    "standing_lanes",
    "whole_lanes",
]
