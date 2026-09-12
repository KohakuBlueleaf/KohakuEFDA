"""The project's router: the framework's lane router with the project's lane order and shape.

The lanes a placement touches are laid pipes first, then by role, then the higher rate,
then the wider span. Only a pipe net with several sources and several sinks has roles
(its trunk, the joins into it, the branches off it); every other lane is plain, and its
rate and span decide. A lane's rate is the flow it is assigned and its span the distance
between the port cells at its two ends. ``ATTACH_MIN_CELLS`` is how many cells of its own
a lane lays before it offers its straight cells to the next lane. ``JOIN_ONLY_LANES`` off
refuses a lane that is only a merge at its source's port cell.
"""

from collections import OrderedDict
from fractions import Fraction
from typing import Any

from kohakuefda.physics.facts import lane_facts, pin_facts, recall, remember
from kohakulayout.ir import PinRef, Refusal
from kohakulayout.ir.geometry import XY
from kohakulayout.state import LaneRouter
from kohakulayout.state.router.lanes import attach_pins, lane_pins
from kohakulayout.state.router.protocol import terminals
from kohakulayout.state.router.trees import Plan, TreePolicy, grow, may_join, seed_of

ATTACH_MIN_CELLS: int = 1
JOIN_ONLY_LANES: bool = True
Pin = tuple[str, str]
Lane = tuple[Pin, Pin, Fraction]


class LaneTable:
    """A net's lane facts read once: lanes, rates, partners, the pipe tree's ends and lane roles."""

    def __init__(self, net: Any) -> None:
        self.facts: list[Lane] = lane_facts(net)
        self.rates: dict[tuple[str, str, str, str], Fraction] = {
            (s[0], s[1], t[0], t[1]): rate for s, t, rate in self.facts
        }
        self.by_pair: dict[tuple[Pin, Pin], Lane] = {}
        self.partners: dict[Pin, list[Pin]] = {}
        load: dict[Pin, Fraction] = {}
        for fact in self.facts:
            source, sink, rate = fact
            self.by_pair.setdefault((source, sink), fact)
            self.partners.setdefault(source, []).append(sink)
            self.partners.setdefault(sink, []).append(source)
            load[source] = load.get(source, Fraction(0)) + rate
            load[sink] = load.get(sink, Fraction(0)) + rate
        self.tree = (
            net.carrier == "pipe" and len(net.sources) > 1 and len(net.sinks) > 1
        )
        self.root: Pin | None = max(
            ((r.cell, r.pin) for r in net.sources),
            key=lambda k: load.get(k, 0),
            default=None,
        )
        self.main: Pin | None = max(
            ((r.cell, r.pin) for r in net.sinks),
            key=lambda k: load.get(k, 0),
            default=None,
        )

    def role(self, source: Pin, sink: Pin) -> int:
        """A lane's role on a pipe tree: 0 the trunk, 1 a join, 3 a branch; 2 elsewhere."""
        if not self.tree:
            return 2
        if (source, sink) == (self.root, self.main):
            return 0
        if sink == self.main:
            return 1
        if source == self.root:
            return 3
        return 2


_TABLES: OrderedDict = OrderedDict()


def table_of(net: Any) -> LaneTable:
    """The net's lane table, built once per net."""
    hit = recall(_TABLES, net)
    return hit if hit is not None else remember(_TABLES, net, LaneTable(net))


class LanePolicy(TreePolicy):
    """The project's tree shape, lane by lane: a pin is reached when a lane of its has both ends placed; a lane joins or leaves a straight cell of the standing lanes, never the bend in front of a port (the port cell behind an attach cell counts); on a pipe tree with several sources and sinks a join stays on the trunk before its first branch and a branch after its last join."""

    def root(self, world: Any, net: Any, sources: list[Any]) -> Any:
        """The source the tree grows from: on a pipe tree its fullest source, else the placed source whose lane to a placed sink carries the most and, at one rate, spans farthest."""
        table = table_of(net)
        rates = table.rates
        if table.tree:
            fullest = max(
                net.sources,
                key=lambda r: sum(
                    v for k, v in rates.items() if k[:2] == (r.cell, r.pin)
                ),
            )
            for t in sources:
                if t.ref == fullest:
                    return t

        def key(t: Any) -> tuple[Any, int]:
            best: tuple[Any, int] = (Fraction(0), 0)
            for (sc, sp, tc, tp), rate in rates.items():
                if (sc, sp) != (t.ref.cell, t.ref.pin) or tc not in world.placements:
                    continue
                goal = world.attach_cell(tc, tp)
                span = (
                    0
                    if goal is None
                    else min(
                        abs(a[0] - goal[0]) + abs(a[1] - goal[1]) for _, a in t.options
                    )
                )
                best = max(best, (rate, span))
            return best

        return max(sources, key=key)

    def trunk(self, world: Any, net: Any, root: Any, sinks: list[Any]) -> list[Any]:
        """The first sink the trunk runs to: on a pipe tree its fullest sink when placed, else the placed sink whose lane carries the most and, at one rate, lies farthest."""
        if root is None or not sinks:
            return sinks
        table = table_of(net)
        rates = table.rates
        if table.tree:
            main = max(
                net.sinks,
                key=lambda r: sum(
                    v for k, v in rates.items() if k[2:] == (r.cell, r.pin)
                ),
            )
            placed_main = [g for g in sinks if g[1] is not None and g[1].ref == main]
            if placed_main:
                return placed_main

        def key(group: Any) -> tuple[Any, int]:
            terminal = group[1]
            rate = rates.get(
                (root.ref.cell, root.ref.pin, terminal.ref.cell, terminal.ref.pin),
                Fraction(0),
            )
            span = min(
                abs(a[0] - b[0]) + abs(a[1] - b[1])
                for _, a in root.options
                for b in group[0]
            )
            return (rate, span)

        return [max((g for g in sinks if g[1] is not None), key=key, default=sinks[0])]

    def lanes(self, world: Any, net: Any) -> list[tuple[Any, Any]]:
        """The net's lanes in laying order: on a pipe tree the trunk, then the joins, then the branches; among equals the higher rate, then the wider span between the two attach cells, then the lane fact's place."""
        table = table_of(net)
        facts = table.facts
        if not facts:
            return super().lanes(world, net)
        ranked = sorted(
            enumerate(facts), key=lambda e: (*lane_key(world, table, e[1]), e[0])
        )
        return [
            (PinRef(cell=s[0], pin=s[1]), PinRef(cell=t[0], pin=t[1]))
            for _, (s, t, _) in ranked
        ]

    def rank(self, world: Any, net: Any, source: Any, sink: Any) -> tuple[Any, ...]:
        """A lane's rank across nets: pipes first, then the role, the higher rate, the wider span."""
        table = table_of(net)
        fact = table.by_pair.get(((source.cell, source.pin), (sink.cell, sink.pin)))
        if fact is not None:
            return (net.carrier != "pipe", *lane_key(world, table, fact))
        return (net.carrier != "pipe", 2, Fraction(0), 0)

    def blockers(
        self, world: Any, net: Any, plan: Plan, source: Any, sink: Any
    ) -> list[tuple[Any, Any]]:
        """On a pipe tree, the attachments a join or a branch with nowhere to attach takes up: for a join every branch leaving the trunk, for a branch every join into it; nothing elsewhere."""
        table = table_of(net)
        if not table.tree:
            return []
        at = trunk_index(net, plan)
        if at is None:
            return []
        root, main = table.root, table.main
        me = ((source.cell, source.pin), (sink.cell, sink.pin))
        joining = me[1] == main and me[0] != root
        branching = me[0] == root and me[1] != main
        if not (joining or branching):
            return []
        trunk = set(plan.segments[at].cells)
        out = []
        for i, (segment, (s, t)) in enumerate(zip(plan.segments, plan.lanes)):
            if i == at or s is None or t is None:
                continue
            pair = ((s.cell, s.pin), (t.cell, t.pin))
            leaves = pair[0] == root and pair[1] != main and segment.cells[0] in trunk
            joins = pair[1] == main and pair[0] != root and segment.cells[-1] in trunk
            if (joining and leaves) or (branching and joins):
                out.append((s, t))
        return out

    def single_cell_lane(
        self, world: Any, net: Any, source: Any, sink: Any, split: bool, merge: bool
    ) -> bool:
        """Whether a one-cell lane may stand: always under ``JOIN_ONLY_LANES``, else only port to port."""
        return JOIN_ONLY_LANES or not (split or merge)

    def native(self, world: Any, net: Any) -> dict[str, Any] | None:
        """The lane policy as data for the native twin; None for a subclass."""
        if type(self) is not LanePolicy:
            return None
        table = table_of(net)
        if table.facts:
            order = [
                [
                    ".".join(s),
                    ".".join(t),
                    [
                        [table.role(s, t), 1],
                        [-Fraction(rate).numerator, Fraction(rate).denominator],
                    ],
                ]
                for s, t, rate in table.facts
            ]
        else:
            order = [
                [str(s), str(t), [[2, 1], [0, 1]]] for s, t in super().lanes(world, net)
            ]
        ends = None
        if table.tree and table.root is not None and table.main is not None:
            ends = [".".join(table.root), ".".join(table.main)]
        return {
            "order": order,
            "span": bool(table.facts),
            "net_key": [[int(net.carrier != "pipe"), 1]],
            "origins": {"kind": "straight", "min_own": ATTACH_MIN_CELLS, "trunk": ends},
            "blockers": (
                {"kind": "trunk", "root": ends[0], "main": ends[1]}
                if ends
                else {"kind": "none"}
            ),
            "single_joins": JOIN_ONLY_LANES,
        }

    def pending(
        self,
        world: Any,
        net: Any,
        found: tuple[Any, ...],
        seed: Any,
    ) -> tuple[Any, ...]:
        """Readiness lane by lane: a pin is reached once one of its lanes has its partner placed; a pin the standing wire holds stays; when that leaves no source or no sink to grow from, every pin stays."""
        on_wire = {c for seg in seed.segments for c in seg.cells} if seed else set()
        partners = table_of(net).partners
        if not partners:
            return found
        kept = tuple(
            t
            for t in found
            if any(attach in on_wire for _, attach in t.options)
            or any(
                mate[0] in world.placements
                for mate in partners.get((t.ref.cell, t.ref.pin), ())
            )
        )
        if not any(t.direction == "out" for t in kept) or not any(
            t.direction == "in" for t in kept
        ):
            return found
        return kept

    def origins(
        self,
        world: Any,
        net: Any,
        plan: Plan,
        junctions: dict[XY, str],
        joinable: frozenset[XY],
        merging: bool,
    ) -> frozenset[XY]:
        """The straight cells of lanes long enough to join, the trunk cut on a pipe tree."""
        if not plan.segments:
            return joinable
        segments = [list(seg.cells) for seg in plan.segments]
        long = laid_enough(segments, ATTACH_MIN_CELLS)
        at = trunk_index(net, plan) if table_of(net).tree else None
        behind = port_cells_behind(world, net, plan.ports)
        if at is None:
            runs = [run for run, kept in zip(segments, long) if kept]
        else:
            trunk = segments[at]
            laid = [list(seg.cells) for seg in plan.standing] or segments
            before = laid.index(trunk) if trunk in laid else at
            earlier = {c for run in laid[:before] for c in run}
            first = 1 if trunk[0] not in behind or trunk[0] in earlier else 0
            last = (
                len(trunk) - 1
                if trunk[-1] not in behind or trunk[-1] in earlier
                else len(trunk)
            )
            if not long[at]:
                runs = []
            elif merging:
                splits = [
                    i
                    for i, c in enumerate(trunk)
                    if i >= first and junctions.get(c) == "split"
                ]
                stop = splits[0] if splits else len(trunk)
                runs = [trunk[: stop + 1]]
            else:
                merges = [
                    i
                    for i, c in enumerate(trunk)
                    if i < last and junctions.get(c) == "merge"
                ]
                start = merges[-1] if merges else 0
                runs = [trunk[start:]]
            runs += [
                run
                for i, (run, kept) in enumerate(zip(segments, long))
                if kept and i != at
            ]
        extended = []
        for run in runs:
            if run[0] in behind:
                run = [behind[run[0]], *run]
            if run[-1] in behind:
                run = [*run, behind[run[-1]]]
            extended.append(run)
        return joinable & straight_cells(extended, open_ends=False)


def trunk_index(net: Any, plan: Plan) -> int | None:
    """Which segment of the plan is a pipe tree's trunk: the first when the plan names no lanes (a tree grown from its root), else the lane between the tree's ends, or None when that lane is not among them."""
    if not plan.lanes:
        return 0
    root, main = tree_ends(net)
    for i, (source, sink) in enumerate(plan.lanes):
        if source is None or sink is None:
            continue
        if (source.cell, source.pin) == root and (sink.cell, sink.pin) == main:
            return i
    return None


def port_cells_behind(world: Any, net: Any, ports: dict[str, str]) -> dict[XY, XY]:
    """The port cell behind each attach cell of the net's placed pins, through the port the plan records or the pin's only one."""
    behind: dict[XY, XY] = {}
    for ref in net.pins():
        choices = world.port_choices(ref.cell).get(ref.pin, ())
        chosen = ports.get(str(ref))
        for port_id, attach, port_cell in choices:
            if chosen is None or port_id == chosen:
                behind[attach] = port_cell
    return behind


def laid_enough(segments: list[list[XY]], minimum: int) -> list[bool]:
    """Which runs laid at least ``minimum`` cells of their own; an end on a run laid before it (the cell it joined or left) is not its own."""
    out = []
    for i, run in enumerate(segments):
        others = {c for other in segments[:i] for c in other}
        own = len(run)
        if run[0] in others:
            own -= 1
        if len(run) > 1 and run[-1] in others:
            own -= 1
        out.append(own >= minimum)
    return out


def straight_cells(runs: list[list[XY]], open_ends: bool = True) -> set[XY]:
    """The cells of the runs a lane may attach at: every cell whose neighbours on the run line up, never a bend; the ends count too unless ``open_ends`` is off, for runs extended by the port cells behind their attach cells."""
    straight: set[XY] = set()
    for run in runs:
        for i, c in enumerate(run):
            if i == 0 or i == len(run) - 1:
                if open_ends:
                    straight.add(c)
                continue
            if run[i - 1][0] == run[i + 1][0] or run[i - 1][1] == run[i + 1][1]:
                straight.add(c)
    return straight


def designated_cell(world: Any, cell_id: str, pin_id: str) -> XY | None:
    """The attach cell of a placed pin's designated port: its first choice."""
    choices = world.port_choices(cell_id).get(pin_id, ())
    return choices[0][1] if choices else None


def span_of(world: Any, source: Pin, sink: Pin) -> int:
    """The Manhattan span between two pins' designated attach cells; zero while one is unplaced."""
    p, q = designated_cell(world, *source), designated_cell(world, *sink)
    return 0 if p is None or q is None else abs(p[0] - q[0]) + abs(p[1] - q[1])


def lane_key(world: Any, table: LaneTable, fact: Lane) -> tuple[int, Fraction, int]:
    """One lane's key: its role on a pipe tree, then the higher rate, then the wider span."""
    source, sink, rate = fact
    return (table.role(source, sink), -rate, -span_of(world, source, sink))


def lane_ends(
    world: Any, net: Any, ref: PinRef, side: int, policy: TreePolicy
) -> frozenset[XY] | None:
    """Where a lane may start (side 0) or end (side 1) on a pin's standing lanes; None without."""
    wire = world.wires.get(net.id)
    found = terminals(world, net)
    if wire is None or isinstance(found, Refusal):
        return None
    segments = list(wire.segments)
    read = lane_pins(segments, attach_pins(found, wire.ports), frozenset(net.sources))
    mine = [i for i, pair in enumerate(read) if pair[side] == ref]
    if not mine:
        return None
    seed = seed_of(world, net)
    if seed is None:
        return None
    own = Plan(net_id=net.id, segments=[segments[i] for i in mine])
    own.ports = dict(wire.ports)
    own.lanes = [read[i] for i in mine]
    own.standing = segments
    rule = world.physics.carriers.junction(net.carrier)
    layer = world.carrier_layer(net.carrier)
    crossed = {xy for xy, _, _ in seed.crossings}
    joinable = frozenset(
        c
        for seg in own.segments
        for c in seg.cells
        if c not in crossed
        and c not in seed.junctions
        and may_join(world, rule, c, layer)
    )
    return policy.origins(world, net, own, dict(seed.junctions), joinable, side == 1)


def tree_ends(net: Any) -> tuple[Pin | None, Pin | None]:
    """A pipe tree's trunk ends: the source and the sink carrying the most; None on a side without pins."""
    table = table_of(net)
    return table.root, table.main


class EndfieldRouter(LaneRouter):
    """The framework's lane router with the project's net order; ``lanes`` installs the project's lane policy, ``wire_model`` picks a bundle of lanes (``lanes``) or one tree per net (``tree``)."""

    id = "endfield"

    def __init__(
        self, *args: Any, lanes: bool = False, wire_model: str = "lanes", **kwargs: Any
    ) -> None:
        super().__init__(*args, **kwargs)
        self.wire_model = wire_model
        if lanes:
            self.policy = LanePolicy()

    def plan(self, world: Any, net: Any, search: Any, seed: Any) -> Any:
        if self.wire_model == "tree":
            return grow(world, net, search, seed, self.policy)
        return super().plan(world, net, search, seed)

    def route(self, world: Any, net_id: str) -> Any:
        if self.wire_model == "tree":
            return LaneRouter.__mro__[1].route(self, world, net_id)
        return super().route(world, net_id)

    def route_all(
        self, world: Any, cell_id: str, pending: list[str], grown: set[str]
    ) -> Any:
        """One tree per net routes the nets in the project's net order; the lane bundle lays their lanes in the project's lane order across nets."""
        if self.wire_model != "tree":
            return super().route_all(world, cell_id, pending, grown)
        for net_id in self.order(world, cell_id, pending, grown):
            refusal = world.route(net_id, grow=net_id in grown)
            if refusal is not None:
                return refusal
        return None

    def order_data(self, world: Any, net: Any) -> dict[str, Any] | None:
        """The net order as data for the native twin; None for a subclass."""
        if type(self) is not EndfieldRouter:
            return None

        def frac(value: Any) -> list[int]:
            value = Fraction(value)
            return [value.numerator, value.denominator]

        def rate(ref: Any) -> Fraction:
            found = pin_facts(world.netlist.cells[ref.cell]).get(ref.pin)
            return net.rate if found is None else found[1]

        facts = table_of(net).facts
        lanes = [[".".join(s), ".".join(t), frac(r)] for s, t, r in facts] or [
            [str(s), str(t), frac(net.rate)] for s in net.sources for t in net.sinks
        ]
        tree = None
        if table_of(net).tree:
            tree = {
                "root": str(max(net.sources, key=rate)),
                "main": str(max(net.sinks, key=rate)),
                "rates": {str(r): frac(rate(r)) for r in net.pins()},
            }
        return {
            "kind": "lanes",
            "key": [[int(net.carrier != "pipe"), 1]],
            "lanes": lanes,
            "rate": frac(net.rate),
            "tree": tree,
        }

    def order(
        self, world: Any, cell_id: str, pending: list[str], grown: set[str]
    ) -> list[str]:
        """The order for the nets a placement touches: pipes first, a pipe tree's trunk before its joins, its joins before its branches, then the lane of the highest rate, then the widest span; a net ranks by the first of its lanes at the new cell."""

        def key(net_id: str) -> tuple[bool, int, Fraction, int]:
            net = world.netlist.nets[net_id]
            lanes = lanes_at(world, net, cell_id)
            rank = 2
            if table_of(net).tree:
                rank, lanes = tree_lane(world, net, cell_id, net_id in grown)
            first = min(
                ((-rate, -span_of(world, a, b)) for a, b, rate in lanes),
                default=(-net.rate, -world.span(net_id)),
            )
            return (net.carrier != "pipe", rank, first[0], first[1])

        return sorted(dict.fromkeys(pending), key=key)


def lanes_at(world: Any, net: Any, cell_id: str) -> list[Lane]:
    """The lanes of a net that end at a cell, or all of them for a net the placement only disturbed; a net without lane facts pairs its sources with its sinks at the net's rate."""
    lanes = table_of(net).facts
    if not lanes:
        lanes = [
            ((s.cell, s.pin), (t.cell, t.pin), net.rate)
            for s in net.sources
            for t in net.sinks
        ]
    at = [lane for lane in lanes if cell_id in (lane[0][0], lane[1][0])]
    return at or lanes


def tree_lane(
    world: Any, net: Any, cell_id: str, is_grown: bool
) -> tuple[int, list[Lane]]:
    """The role and lane for a pipe tree at a cell: the trunk from the fullest source to the fullest sink while nothing stands or when the cell holds no pin of it, a join from the cell's source to that sink, a branch from that source to the cell's sink."""

    def rate(ref: Any) -> Fraction:
        found = pin_facts(world.netlist.cells[ref.cell]).get(ref.pin)
        return net.rate if found is None else found[1]

    root = max(net.sources, key=rate)
    main = max(net.sinks, key=rate)
    pin = lambda ref: (ref.cell, ref.pin)
    joins = [(pin(r), pin(main), rate(r)) for r in net.sources if r.cell == cell_id]
    leaves = [(pin(root), pin(r), rate(r)) for r in net.sinks if r.cell == cell_id]
    if not is_grown or not (joins or leaves):
        return 0, [(pin(root), pin(main), rate(root))]
    return (1, joins) if joins else (3, leaves)


__all__ = [
    "EndfieldRouter",
    "LanePolicy",
    "LaneTable",
    "lanes_at",
    "port_cells_behind",
    "straight_cells",
    "table_of",
    "tree_lane",
]
