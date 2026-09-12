"""Trees: one net with many terminals grown nearest-first, junctions per the pack's rule."""

from collections.abc import Iterable
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Any

from kohakulayout.ir import Refusal, Segment
from kohakulayout.ir.geometry import XY
from kohakulayout.state.crossing import crossable, occluded_free, unit_allowed
from kohakulayout.state.kernel import holder_kind
from kohakulayout.state.router.pathfinder import Search, find
from kohakulayout.state.router.protocol import Terminal, refuse, terminals


@dataclass
class Plan:
    """What a routed net will become, before anything is written to the world.

    ``lanes`` names each segment's source and sink pin under the lane router; ``standing``
    holds the whole plan's segments when this plan is one pin's part of it.
    """

    net_id: str
    segments: list[Segment] = field(default_factory=list)
    crossings: list[tuple[XY, str, bool]] = field(default_factory=list)
    junctions: list[tuple[XY, str]] = field(default_factory=list)
    rips: set[str] = field(default_factory=set)
    displaced: set[str] = field(default_factory=set)
    ports: dict[str, str] = field(default_factory=dict)
    lanes: list[tuple[Any, Any]] = field(default_factory=list)
    cost: int = 0
    standing: list[Segment] = field(default_factory=list)


@dataclass
class Seed:
    """A net's standing tree, so a grow reaches only the pins it does not touch yet: its segments in travel order, its junctions and crossings, the ports it uses."""

    segments: list[Segment]
    junctions: dict[XY, str]
    crossings: list[tuple[XY, str, bool]]
    ports: dict[str, str]


def seed_of(world: Any, net: Any) -> Seed | None:
    """The seed a routed net gives a grow, read before its wire is taken up: its junctions, and a crossing at every cell another wire holds or its own crossing unit stands on (two of its lanes), since taking the wire up drops the units that stood for them; None when it has no wire."""
    wire = world.wires.get(net.id)
    if wire is None:
        return None
    rule = world.physics.carriers.junction(net.carrier)
    kinds = {
        fp.id: name
        for name, fp in (("split", rule.split), ("merge", rule.merge))
        if fp is not None
    }
    layer = world.carrier_layer(net.carrier)
    junctions: dict[XY, str] = {}
    for unit_id in wire.units:
        unit = world.units.get(unit_id)
        if unit is not None and unit.footprint in kinds:
            junctions[(unit.x, unit.y)] = kinds[unit.footprint]
    crossings: list[tuple[XY, str, bool]] = []
    for xy in sorted(wire.cells()):
        for holder in world.kernel.holders_at(layer, xy):
            kind, ref = holder_kind(holder)
            if kind == "wire" and ref != net.id:
                crossings.append((xy, ref, False))
                break
    own = world.physics.carriers.crossing(net.carrier, net.carrier)
    seen = {xy for xy, _, _ in crossings}
    if own.mode == "unit" and own.unit is not None:
        for unit_id in wire.units:
            unit = world.units.get(unit_id)
            if unit is None or unit.footprint != own.unit.id:
                continue
            xy = (unit.x, unit.y)
            if xy not in seen:
                crossings.append((xy, net.id, False))
    return Seed(list(wire.segments), junctions, crossings, dict(wire.ports))


def may_join(world: Any, rule: Any, cell: XY, layer: str = "") -> bool:
    """Whether a junction unit could stand on this tree cell: allowed there and free of units."""
    if rule.mode != "unit":
        return True
    if layer and any(
        str(h).startswith("unit:") for h in world.kernel.holders_at(layer, cell)
    ):
        return False
    return all(
        fp is None or (unit_allowed(world, fp, cell) and occluded_free(world, fp, cell))
        for fp in (rule.split, rule.merge)
    )


def feeds(terminal: Terminal | None) -> bool:
    """Whether a terminal sends flow into the tree: a source's port, or the outside."""
    return terminal is None or terminal.direction == "out"


def held_by_others(world: Any, search: Search, cell: XY) -> frozenset[str] | None:
    """The nets whose wires hold a terminal cell and must be ripped for the search to start there, a wire the path may cross on it not among them; None when the cell cannot be taken: a footprint or another net's unit stands on it (a field emitter is displaced by the path)."""
    mine = search.occupant(search.net_id, search.carrier)
    wires: set[str] = set()
    units = False
    for holder in world.kernel.holders_at(search.layer, cell):
        kind, ref = holder_kind(holder)
        if kind == "cell":
            return None
        if kind == "unit":
            owner = world.units[ref].owner
            if owner.startswith("field:"):
                continue
            if owner != f"net:{search.net_id}":
                return None
            units = True
        elif kind == "wire" and ref != search.net_id:
            other = world.netlist.nets[ref]
            if world.share.may_share(mine, search.occupant(ref, other.carrier)):
                continue
            if crossable(world, search.layer, search.carrier, ref, cell):
                continue
            wires.add(ref)
    if not wires:
        return frozenset()
    if units or not search.allow_rip or wires & search.protected:
        return None
    return frozenset(wires)


class TreePolicy:
    """What a router may decide about a tree's shape: which sinks the trunk may end at, and which tree cells a join or a branch may leave from; the default keeps every option."""

    def root(self, world: Any, net: Any, sources: list[Terminal]) -> Terminal:
        """The placed source the tree grows from; the default takes the first."""
        return sources[0]

    def trunk(self, world: Any, net: Any, root: Any, sinks: list[Any]) -> list[Any]:
        """The placed sink groups the trunk from ``root`` may end at; the default keeps every one, so the nearest wins."""
        return sinks

    def pending(
        self, world: Any, net: Any, found: tuple[Terminal, ...], seed: Seed | None
    ) -> tuple[Terminal, ...]:
        """The placed pins this grow must reach; the default reaches every one."""
        return found

    def lanes(self, world: Any, net: Any) -> list[tuple[Any, Any]]:
        """The net's lanes as source and sink pins in laying order, for a router that lays lanes; the default runs the first source to every sink and every other source to the first sink."""
        if not net.sources or not net.sinks:
            return []
        return [(net.sources[0], t) for t in net.sinks] + [
            (s, net.sinks[0]) for s in net.sources[1:]
        ]

    def rank(self, world: Any, net: Any, source: Any, sink: Any) -> tuple[Any, ...]:
        """Where a lane stands in the order the lanes of several nets are laid in, the smallest first; the default ranks every lane alike, so nets go one after another in the router's net order."""
        return ()

    def blockers(
        self, world: Any, net: Any, plan: Plan, source: Any, sink: Any
    ) -> list[tuple[Any, Any]]:
        """The standing lanes a lane with no cell to start from or end on may take up, to be laid again after it; the default takes up none."""
        return []

    def single_cell_lane(
        self, world: Any, net: Any, source: Any, sink: Any, split: bool, merge: bool
    ) -> bool:
        """Whether a lane may be one cell (its two pins' attach cells or a lane of one of them coinciding), with ``split`` when that cell lies on a lane of its source and ``merge`` when on a lane of its sink; the default allows every one."""
        return True

    def origins(
        self,
        world: Any,
        net: Any,
        plan: Plan,
        junctions: dict[XY, str],
        joinable: frozenset[XY],
        merging: bool,
    ) -> frozenset[XY]:
        return joinable

    def native(self, world: Any, net: Any) -> dict[str, Any] | None:
        """The policy as data for the native twin; None when it overrides a hook data cannot say.

        The default keeps its lanes' order, ranks them alike and allows every origin and one-cell
        lane.
        """
        if any(
            getattr(type(self), hook) is not getattr(TreePolicy, hook)
            for hook in ("lanes", "rank", "origins", "blockers", "single_cell_lane")
        ):
            return None
        return {
            "order": [[str(s), str(t), []] for s, t in self.lanes(world, net)],
            "span": False,
            "net_key": [],
            "origins": {"kind": "all"},
            "blockers": {"kind": "none"},
            "single_joins": True,
        }


DEFAULT_POLICY = TreePolicy()


def grow(
    world: Any,
    net: Any,
    search: Search,
    seed: Seed | None = None,
    policy: TreePolicy = DEFAULT_POLICY,
) -> Plan | Refusal:
    """A plan connecting every terminal of ``net`` the policy holds pending: a trunk from the root to the nearest sink, then the sources join the tree with a merge wherever flow already arrives, then the other sinks leave the tree with a split wherever flow already leaves; a path never runs through a terminal it is not reaching, so every cell carries flow one way toward a sink and no cell holds two junctions. With a ``seed`` the standing tree is kept (a segment ending on a source's attach cell flows tree-ward, so it is read the other way) and only the pins off it get a path; a pin whose attach cell the tree already crosses is seated there with its junction and no path."""
    found = terminals(world, net)
    if isinstance(found, Refusal):
        return found
    found = tuple(policy.pending(world, net, found, seed))
    fed = [t for t in found if t.direction == "out"]
    if len(fed) > 1 and seed is None:
        first = policy.root(world, net, fed)
        found = (first, *(t for t in found if t is not first))
    edge = world.physics.boundaries.outside(world, net)
    if not found and not edge:
        return refuse(net.id, "no terminals")
    rule = world.physics.carriers.junction(net.carrier)
    groups: list[tuple[frozenset[XY], Terminal | None]] = [
        (frozenset(attach for _, attach in t.options), t) for t in found
    ]
    port_at = {(str(t.ref), attach): port for t in found for port, attach in t.options}
    if edge:
        groups.append((frozenset(edge), None))
    if rule.mode == "forbidden" and len(groups) > 2:
        return refuse(
            net.id,
            f"{len(groups)} terminals need a junction, which {net.carrier!r} forbids",
        )
    plan = Plan(net_id=net.id)

    sat: dict[XY, set[str]] = {}

    def took(terminal: Terminal | None, cell: XY) -> None:
        """Record the port a pin with a choice is reached through, and that the pin's cell sits there."""
        if terminal is None:
            return
        sat.setdefault(cell, set()).add(terminal.ref.cell)
        if not terminal.bound:
            plan.ports[str(terminal.ref)] = port_at[(str(terminal.ref), cell)]

    def sibling(a: Terminal | None, b: Terminal | None) -> bool:
        return a is not None and b is not None and a.ref.cell == b.ref.cell

    def open_for(terminal: Terminal | None, cells: Iterable[XY]) -> list[XY]:
        """The cells no sibling pin of the terminal's cell sits on, sorted; a port serves one pin of a cell."""
        if terminal is None:
            return sorted(cells)
        return sorted(c for c in cells if terminal.ref.cell not in sat.get(c, ()))

    tree: set[XY] = set()
    arrivals: dict[XY, int] = {}
    departures: dict[XY, int] = {}
    junction_at: dict[XY, str] = {}
    crossed: set[XY] = set()
    reached: set[XY] = set()
    pending = groups[1:]
    root_cells, root = groups[0]
    if seed is not None:
        ends = {c for seg in seed.segments for c in (seg.cells[0], seg.cells[-1])}
        hits = []
        seats: dict[int, XY] = {}
        for g in groups:
            recorded = seed.ports.get(str(g[1].ref)) if g[1] is not None else None
            own = open_for(g[1], g[0] & ends)
            if recorded is not None:
                own = [
                    c for c in own if port_at.get((str(g[1].ref), c)) == recorded
                ] or own
            if own:
                hits.append(g)
                seats[id(g)] = own[0]
                took(g[1], own[0])
        if not hits:
            seed = None
            sat.clear()
            plan.ports.clear()
    if seed is not None:
        fed_from = {c for cells, t in groups if feeds(t) for c in cells}
        drained = {c for cells, t in groups if not feeds(t) for c in cells}
        for segment in seed.segments:
            run = list(segment.cells)
            if run[-1] in fed_from and run[-1] not in drained:
                run.reverse()
            for a, b in pairwise(run):
                departures[a] = departures.get(a, 0) + 1
                arrivals[b] = arrivals.get(b, 0) + 1
            tree.update(segment.cells)
        for g in hits:
            _, terminal = g
            cell = seats[id(g)]
            flow = arrivals if feeds(terminal) else departures
            flow[cell] = flow.get(cell, 0) + 1
            reached.add(cell)
        junction_at.update(seed.junctions)
        crossed.update(xy for xy, _, _ in seed.crossings)
        plan.segments.extend(seed.segments)
        plan.crossings.extend(seed.crossings)
        root_cells, root = hits[0]
        root_cells = frozenset(root_cells & reached)
        pending = [g for g in groups if g not in hits]
    open_root: set[XY] = set(root_cells & tree)
    for cell in root_cells - tree:
        intruders = held_by_others(world, search, cell)
        if intruders is None:
            continue
        plan.rips |= intruders
        open_root.add(cell)
    if not open_root:
        return refuse(net.id, f"its cell {min(root_cells)} is held by another net")
    root_cells = frozenset(open_root)
    settled = bool(tree)
    if not tree:
        tree.update(root_cells)
        for cell in root_cells:
            if feeds(root):
                arrivals[cell] = 1
            else:
                departures[cell] = 1
    trunk_laid = not feeds(root) or bool(seed)

    standing: dict[XY, bool] = {}

    def stands(cell: XY) -> bool:
        """Whether a junction may be made at this tree cell: free junctions anywhere, a unit off crossings and other units; each cell is asked once per grow."""
        if rule.mode != "unit":
            return True
        if cell in crossed:
            return False
        found = standing.get(cell)
        if found is None:
            found = standing[cell] = may_join(world, rule, cell, search.layer)
        return found

    def may_seat(cell: XY, merging: bool) -> bool:
        """Whether a pin may join the tree on its own attach cell: no flow yet the other way, or a junction of the right kind may stand there."""
        if merging:
            return arrivals.get(cell, 0) == 0 or (
                junction_at.get(cell, "merge") == "merge" and stands(cell)
            )
        return departures.get(cell, 0) == 0 or (
            junction_at.get(cell, "split") == "split" and stands(cell)
        )

    done: set[int] = set()
    for _ in range(len(pending)):
        remaining = []
        for index, g in enumerate(pending):
            if index in done:
                continue
            free_cells = frozenset(open_for(g[1], g[0] - reached))
            shared = free_cells & tree
            if seed is None and shared and (settled or not sibling(g[1], root)):
                cell = min(shared)
                if not settled:
                    took(root, cell)
                    for other in root_cells - {cell}:
                        tree.discard(other)
                        arrivals.pop(other, None)
                        departures.pop(other, None)
                    root_cells = frozenset({cell})
                    settled = True
                took(g[1], cell)
                reached.add(cell)
                done.add(index)
                continue
            remaining.append((index, (free_cells, g[1])))
        if not remaining:
            break
        seated = next(
            (
                (index, g, cell)
                for index, g in remaining
                for cell in open_for(g[1], g[0] & tree)
                if settled and may_seat(cell, feeds(g[1]))
            ),
            None,
        )
        if seated is not None:
            index, (_, terminal), cell = seated
            done.add(index)
            took(terminal, cell)
            if feeds(terminal):
                if arrivals.get(cell, 0) >= 1:
                    junction_at.setdefault(cell, "merge")
                arrivals[cell] = arrivals.get(cell, 0) + 1
            else:
                if departures.get(cell, 0) >= 1:
                    junction_at.setdefault(cell, "split")
                departures[cell] = departures.get(cell, 0) + 1
            reached.add(cell)
            continue
        sources = [(i, g) for i, g in remaining if feeds(g[1])]
        sinks = [(i, g) for i, g in remaining if not feeds(g[1])]
        if not trunk_laid and sinks:
            main = policy.trunk(world, net, root, [g for _, g in sinks])
            chosen = [(i, g) for i, g in sinks if g in main] or sinks
            merging = False
        elif sources:
            chosen, merging = sources, True
        else:
            chosen, merging = sinks, False
        targets = frozenset().union(*(g[0] for _, g in chosen))
        starts = frozenset(tree)
        if merging:
            joinable = frozenset(
                c
                for c in starts
                if arrivals.get(c, 0) == 0
                or (junction_at.get(c, "merge") == "merge" and stands(c))
            )
        else:
            joinable = frozenset(
                c
                for c in starts
                if departures.get(c, 0) == 0
                or (junction_at.get(c, "split") == "split" and stands(c))
            )
        origins = policy.origins(world, net, plan, junction_at, joinable, merging)
        if not origins:
            return refuse(net.id, "no tree cell a lane may attach at")
        others = frozenset().union(
            *(g[0] for _, g in remaining if not (g[0] & targets)), frozenset()
        )
        path = find(search, origins, targets, (frozenset(tree) - origins) | others)
        if path is None:
            return refuse(
                net.id,
                f"no path from {min(origins)} to any of {sorted(targets)[:4]}",
            )
        join, end = path.cells[0], path.cells[-1]
        if not settled:
            took(root, join)
            reached.add(join)
            for cell in root_cells - set(path.cells):
                tree.discard(cell)
                arrivals.pop(cell, None)
                departures.pop(cell, None)
            settled = True
        index, (_, terminal) = next((i, g) for i, g in chosen if end in g[0])
        done.add(index)
        took(terminal, end)
        for cell in path.cells[1:-1]:
            arrivals[cell] = arrivals.get(cell, 0) + 1
            departures[cell] = departures.get(cell, 0) + 1
        if merging:
            if len(path.cells) > 1 and arrivals.get(join, 0) >= 1:
                junction_at.setdefault(join, "merge")
            arrivals[join] = arrivals.get(join, 0) + 1
        else:
            if len(path.cells) > 1 and departures.get(join, 0) >= 1:
                junction_at.setdefault(join, "split")
            departures[join] = departures.get(join, 0) + 1
            trunk_laid = True
        arrivals[end] = arrivals.get(end, 0) + 1
        departures[end] = departures.get(end, 0) + 1
        tree.update(path.cells)
        reached.add(end)
        crossed.update(xy for xy, _, _ in path.crossings)
        plan.segments.append(
            Segment(carrier=net.carrier, layer=search.layer, cells=path.cells)
        )
        plan.crossings.extend(path.crossings)
        plan.rips |= path.rips
        plan.displaced |= path.displaces
        plan.cost += path.cost
    plan.junctions.extend(junction_at.items())
    if not plan.segments:
        only = single_cell(world, net, search, root, root_cells, plan)
        if only is None:
            return refuse(net.id, "its only cell is held by another net")
        took(root, only)
        plan.segments.append(
            Segment(carrier=net.carrier, layer=search.layer, cells=(only,))
        )
    return plan


def single_cell(
    world: Any,
    net: Any,
    search: Search,
    root: Terminal | None,
    root_cells: frozenset[XY],
    plan: Plan,
) -> XY | None:
    """The one cell a wire with no path stands on: the root's own attach cell when free, else any free root cell, else a root cell one foreign wire runs straight through, crossed there with its unit; None when every root cell is held."""
    ordered = sorted(root_cells, key=lambda c: (root is None or c != root.cell, c))
    foreign: dict[XY, list[str]] = {}
    for cell in ordered:
        foreign[cell] = [
            ref
            for holder in world.kernel.holders_at(search.layer, cell)
            for kind, ref in (holder_kind(holder),)
            if kind == "wire" and ref != net.id
        ]
        if not foreign[cell]:
            return cell
    for cell in ordered:
        if len(foreign[cell]) != 1:
            continue
        other = foreign[cell][0]
        if crossable(world, search.layer, search.carrier, other, cell):
            plan.crossings.append((cell, other, False))
            return cell
    return None


__all__ = [
    "DEFAULT_POLICY",
    "Plan",
    "Seed",
    "TreePolicy",
    "feeds",
    "grow",
    "held_by_others",
    "may_join",
    "seed_of",
    "single_cell",
]
