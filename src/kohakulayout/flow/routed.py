"""The routed evaluator: rates per run, per unit and per pin over a layout's wires, commodities kept apart.

A wire is read as nodes and runs: a node is a pin (at its attach cell), a unit, a cell
where the wire branches without a unit, or a dangling end; a run is the path between two
nodes, in the segment's own cell order when the layout is ``oriented``, else turned toward
the sink pins. A crossing unit is one node per way of travel, so what enters from one side
leaves by the opposite side. A pin whose attach cell holds a unit, and two
pins on one cell, are joined by a run of no cells; the pack's ``links`` add runs of no
cells and no capacity between pins off the grid. Each round every cell accepts on its in
runs what its pack says and makes what its pack says, sharing each commodity over the runs
that accept; every unit accepts what its merge may bring, passes what the pack lets
through and shares it; then every run carries what was offered, scaled to what it accepts
and its carrier holds. The rounds stop when nothing moves, when rounding to a denominator
gives a fixed point, or when the largest move falls under ``epsilon``.
"""

from dataclasses import dataclass, field
from fractions import Fraction
from itertools import pairwise
from typing import Any

from kohakulayout.flow.findings import capacity as capacity_finding
from kohakulayout.flow.findings import starved, unstable
from kohakulayout.flow.fixedpoint import Evaluation
from kohakulayout.ir import Layout, Netlist
from kohakulayout.ir.geometry import rotate_side

MAX_ROUNDS = 1000
EPSILON = Fraction(1, 1_000_000)
SNAP = 3600
SNAP_EVERY = 25
XY = tuple[int, int]
Mix = dict[str, Fraction]


@dataclass
class Node:
    id: str
    kind: str
    cell: str = ""
    pin: str = ""
    unit: str = ""
    direction: str = ""
    axis: str = ""


@dataclass
class Run:
    id: str
    net: str
    source: str
    target: str
    cells: tuple[XY, ...]
    carrier: str | None
    capacity: Fraction | None


@dataclass
class RunFlow:
    id: str
    net: str
    cells: tuple[XY, ...]
    carrier: str | None
    mix: Mix
    total: Fraction
    capacity: Fraction | None
    source: str
    target: str


@dataclass
class CellFlow:
    id: str
    received: dict[str, Mix] = field(default_factory=dict)
    outputs: dict[str, Mix] = field(default_factory=dict)
    made: Mix = field(default_factory=dict)
    load: Fraction | None = None
    note: str = ""


def _add(mix: Mix, key: str, rate: Fraction) -> None:
    if rate > 0:
        mix[key] = mix.get(key, Fraction(0)) + rate


def _total(mix: Mix) -> Fraction:
    return sum(mix.values(), Fraction(0))


class Graph:
    """The nodes and runs of every wire of a layout, oriented from the source pins."""

    def __init__(
        self, netlist: Netlist, layout: Layout, flow: Any, oriented: bool = False
    ) -> None:
        self.netlist = netlist
        self.layout = layout
        self.flow = flow
        self.oriented = oriented
        self.nodes: dict[str, Node] = {}
        self.runs: dict[str, Run] = {}
        self.pins_of_cell: dict[str, list[Node]] = {}
        self.units: list[Node] = []
        self.branches: list[Node] = []
        for cell_id in netlist.cells:
            for pin in netlist.pins_of(cell_id):
                self.pin_node(cell_id, pin.id, pin.direction)
        for net_id, wire in layout.wires.items():
            self.read_wire(net_id, wire)
        order = {unit_id: index for index, unit_id in enumerate(layout.units)}
        self.units.sort(key=lambda node: (order.get(node.unit, len(order)), node.id))
        for source_cell, out_pin, target_cell, in_pin in flow.links(netlist):
            a = self.pin_node(source_cell, out_pin, "out")
            b = self.pin_node(target_cell, in_pin, "in")
            self.add_run(f"link:{a.id}:{b.id}", "", a.id, b.id, (), None, None)

    def pin_node(self, cell_id: str, pin_id: str, direction: str) -> Node:
        key = f"{cell_id}.{pin_id}"
        node = self.nodes.get(key)
        if node is None:
            node = Node(
                id=key, kind="pin", cell=cell_id, pin=pin_id, direction=direction
            )
            self.nodes[key] = node
            self.pins_of_cell.setdefault(cell_id, []).append(node)
        return node

    def add_run(
        self,
        run_id: str,
        net_id: str,
        source: str,
        target: str,
        cells: tuple[XY, ...],
        carrier: str | None,
        capacity: Fraction | None,
    ) -> None:
        self.runs[run_id] = Run(
            run_id, net_id, source, target, cells, carrier, capacity
        )

    def read_wire(self, net_id: str, wire: Any) -> None:
        net = self.netlist.nets.get(net_id)
        if net is None:
            return
        links: dict[XY, set[XY]] = {}
        for segment in wire.segments:
            for xy in segment.cells:
                links.setdefault(xy, set())
            for a, b in pairwise(segment.cells):
                links[a].add(b)
                links[b].add(a)
        at: dict[XY, list[Node]] = {}
        for ref in net.pins():
            xy = self.layout.attach(self.netlist, ref, wire.port_of(ref))
            if xy is None:
                continue
            pin = self.netlist.pin(ref)
            node = self.pin_node(ref.cell, ref.pin, pin.direction if pin else "in")
            node.axis = self.pin_axis(ref, wire.port_of(ref))
            at.setdefault(xy, []).append(node)
        for unit_id in wire.units:
            unit = self.layout.units.get(unit_id)
            if unit is None:
                continue
            axes = ("N", "E", "S", "W") if self.flow.crosses(unit) else ("",)
            for axis in axes:
                suffix = f":{axis}" if axis else ""
                node = Node(
                    id=f"{net_id}/{unit_id}{suffix}",
                    kind="unit",
                    unit=unit_id,
                    axis=axis,
                )
                self.nodes[node.id] = node
                self.units.append(node)
                at.setdefault((unit.x, unit.y), []).append(node)
        ends = {seg.cells[0] for seg in wire.segments if seg.cells} | {
            seg.cells[-1] for seg in wire.segments if seg.cells
        }
        for xy, near in links.items():
            if xy in at:
                continue
            if len(near) > 2:
                kind = "branch"
            elif len(near) < 2:
                kind = "end"
            elif xy in ends:
                kind = "pass"
            else:
                continue
            node = Node(id=f"{net_id}/{kind}{xy[0]}_{xy[1]}", kind=kind)
            self.nodes[node.id] = node
            if kind != "end":
                self.branches.append(node)
            at[xy] = [node]
        carrier = net.carrier
        capacity = self.capacity_of(carrier)
        for xy, nodes in at.items():
            self.join_at(net_id, xy, nodes, links, carrier, capacity)
        count = 0
        for segment in wire.segments:
            path: list[XY] = []
            for xy in segment.cells:
                path.append(xy)
                if len(path) > 1 and xy in at:
                    count = self.add_path(net_id, path, at, carrier, capacity, count)
                    path = [xy]
            if len(path) > 1:
                count = self.add_path(net_id, path, at, carrier, capacity, count)
        if not self.oriented:
            self.orient(net_id)

    def add_path(
        self,
        net_id: str,
        path: list[XY],
        at: dict[XY, list[Node]],
        carrier: str,
        capacity: Fraction | None,
        count: int,
    ) -> int:
        """One run along ``path`` in the segment's order, between the nodes of its end cells."""
        start = self.anchor(at.get(path[0], []), "out", _heading(path[0], path[1]))
        stop = self.anchor(at.get(path[-1], []), "in", _heading(path[-2], path[-1]))
        self.add_run(
            f"{net_id}/{count}",
            net_id,
            start.id,
            stop.id,
            tuple(path),
            carrier,
            capacity,
        )
        return count + 1

    def pin_axis(self, ref: Any, port_id: str | None) -> str:
        """The way flow travels through a pin's attach cell: out of the port's side for an out pin, into it for an in pin."""
        fp = self.netlist.footprint_for(ref.cell)
        placement = self.layout.placements.get(ref.cell)
        pin = self.netlist.pin(ref)
        if fp is None or placement is None or pin is None or not pin.ports:
            return ""
        port = fp.port(port_id if port_id in pin.ports else pin.ports[0])
        if port is None:
            return ""
        side = rotate_side(port.side, placement.rot)
        return side if pin.direction == "out" else OPPOSITE[side]

    def join_at(
        self,
        net_id: str,
        xy: XY,
        nodes: list[Node],
        links: dict[XY, set[XY]],
        carrier: str,
        capacity: Fraction | None,
    ) -> None:
        """Pins and a unit on one cell: each pin joined to the unit of its axis by a run of no cells, or an out pin to an in pin by a run of that one cell."""
        units = [n for n in nodes if n.kind == "unit"]
        pins = [n for n in nodes if n.kind == "pin"]
        if units:
            for pin in pins:
                unit = next((u for u in units if u.axis == pin.axis), None) or next(
                    (u for u in units if not u.axis), units[0]
                )
                a, b = (pin, unit) if pin.direction == "out" else (unit, pin)
                self.add_run(
                    f"{net_id}/{a.id}>{b.id}", net_id, a.id, b.id, (), None, None
                )
            return
        outs = [p for p in pins if p.direction == "out"]
        ins = [p for p in pins if p.direction == "in"]
        if outs and ins and not links.get(xy):
            for a in outs:
                for b in ins:
                    self.add_run(
                        f"{net_id}/{a.id}>{b.id}",
                        net_id,
                        a.id,
                        b.id,
                        (xy,) if xy in links else (),
                        carrier,
                        capacity,
                    )

    @staticmethod
    def anchor(nodes: list[Node], direction: str, axis: str = "") -> Node:
        """The node a run leaves from or arrives at on a cell: the crossing node of the run's heading, a unit or branch there, else the pin facing that way, else any."""
        for node in nodes:
            if node.kind == "unit" and node.axis == axis:
                return node
        for node in nodes:
            if node.kind in ("unit", "branch", "pass", "end") and not node.axis:
                return node
        for node in nodes:
            if node.kind == "pin" and node.direction == direction:
                return node
        return nodes[0]

    def capacity_of(self, carrier: str) -> Fraction | None:
        return None

    def orient(self, net_id: str) -> None:
        """Runs of the net turned toward its sink pins: from the end farther from a sink to the nearer, ties in the segment's order; a net without sinks flows away from its sources."""
        runs = [r for r in self.runs.values() if r.net == net_id]
        by_node: dict[str, list[Run]] = {}
        for run in runs:
            by_node.setdefault(run.source, []).append(run)
            by_node.setdefault(run.target, []).append(run)
        pins = {
            direction: {
                n.id
                for n in self.nodes.values()
                if n.kind == "pin" and n.direction == direction and n.id in by_node
            }
            for direction in ("in", "out")
        }
        ends = {
            n.id for n in self.nodes.values() if n.kind == "end" and n.id in by_node
        }
        to_sink = _distances(pins["in"] | ends, by_node)
        from_source = _distances(pins["out"], by_node)
        for run in runs:
            near, far = to_sink.get(run.source), to_sink.get(run.target)
            if near is not None and far is not None:
                backwards = near < far or (near == far and run.target in pins["out"])
            else:
                near, far = from_source.get(run.source), from_source.get(run.target)
                if near is None or far is None:
                    continue
                backwards = near > far or (near == far and run.target in pins["out"])
            if backwards:
                run.source, run.target = run.target, run.source

    def runs_into(self, node_id: str) -> list[Run]:
        return [r for r in self.runs.values() if r.target == node_id]

    def runs_out_of(self, node_id: str) -> list[Run]:
        return [r for r in self.runs.values() if r.source == node_id]


class LayoutGraph(Graph):
    def __init__(
        self,
        netlist: Netlist,
        layout: Layout,
        flow: Any,
        fabric: Any,
        oriented: bool = False,
    ) -> None:
        self.fabric = fabric
        super().__init__(netlist, layout, flow, oriented)

    def capacity_of(self, carrier: str) -> Fraction | None:
        if self.fabric is None:
            return None
        found = self.fabric.carriers.get(carrier)
        return (
            None
            if found is None or found.capacity is None
            else Fraction(found.capacity)
        )


class Routed:
    id = "routed"

    def __init__(
        self,
        max_rounds: int = MAX_ROUNDS,
        epsilon: Fraction = EPSILON,
        snap: int = SNAP,
        snap_every: int = SNAP_EVERY,
        oriented: bool = False,
    ) -> None:
        self.max_rounds = max_rounds
        self.epsilon = Fraction(epsilon)
        self.snap = snap
        self.snap_every = snap_every
        self.oriented = oriented

    def evaluate(
        self, netlist: Netlist, flow: Any, fabric: Any = None, layout: Any = None
    ) -> Evaluation:
        if layout is None:
            raise ValueError("the routed evaluator needs a layout")
        flat = netlist.flatten()
        graph = LayoutGraph(flat, layout.flatten(flat), flow, fabric, self.oriented)
        state = _State(graph, flat, flow)
        converged = False
        rounds = 0
        for rounds in range(1, self.max_rounds + 1):
            before = state.snapshot()
            state.step()
            delta = state.delta(before, state.snapshot())
            if delta == 0:
                converged = True
                break
            if (
                delta < self.epsilon or rounds % self.snap_every == 0
            ) and state.settles(self.snap):
                converged = True
                break
            if delta < self.epsilon:
                converged = True
                break
        return state.result(rounds, converged)


class _State:
    """The numbers one evaluation carries between rounds."""

    def __init__(self, graph: Graph, netlist: Netlist, flow: Any) -> None:
        self.graph = graph
        self.netlist = netlist
        self.flow = flow
        self.into: dict[str, list[Run]] = {}
        self.out_of: dict[str, list[Run]] = {}
        for run in graph.runs.values():
            self.into.setdefault(run.target, []).append(run)
            self.out_of.setdefault(run.source, []).append(run)
        self.flows: dict[str, Mix] = {r: {} for r in graph.runs}
        self.offered: dict[str, Mix] = {r: {} for r in graph.runs}
        self.accepted: dict[str, Fraction | None] = {
            r: run.capacity for r, run in graph.runs.items()
        }
        self.seen: dict[str, set[str]] = {r: set() for r in graph.runs}
        self.cells: dict[str, CellFlow] = {}
        self.commodity: dict[str, str] = {}
        for node in graph.nodes.values():
            if node.kind == "pin" and node.direction == "out":
                cell = netlist.cells.get(node.cell)
                self.commodity[node.id] = (
                    flow.commodity(cell, node.pin) if cell is not None else node.id
                )

    # ----------------------------------------------------------- rounds
    def snapshot(self) -> dict[str, Fraction]:
        out: dict[str, Fraction] = {}
        for run_id, mix in self.flows.items():
            for key, rate in mix.items():
                out[f"flow:{run_id}:{key}"] = rate
            accepted = self.accepted[run_id]
            if accepted is not None:
                out[f"accept:{run_id}"] = accepted
        return out

    @staticmethod
    def delta(before: dict[str, Fraction], after: dict[str, Fraction]) -> Fraction:
        worst = Fraction(0)
        for key in set(before) | set(after):
            gap = abs(after.get(key, Fraction(0)) - before.get(key, Fraction(0)))
            worst = max(worst, gap)
        return worst

    def settles(self, snap: int) -> bool:
        """Whether the flows rounded to ``snap`` are a fixed point of one more round."""
        for run_id, mix in self.flows.items():
            self.flows[run_id] = {k: v.limit_denominator(snap) for k, v in mix.items()}
            accepted = self.accepted[run_id]
            if accepted is not None:
                self.accepted[run_id] = accepted.limit_denominator(snap)
        snapped = self.snapshot()
        self.step()
        return self.delta(snapped, self.snapshot()) == 0

    def step(self) -> None:
        for cell_id in self.netlist.cells:
            self.cell_round(cell_id)
        for node in self.graph.units:
            self.unit_round(node)
        for node in self.graph.branches:
            self.unit_round(node)
        for run_id, run in self.graph.runs.items():
            offered = self.offered[run_id]
            total = _total(offered)
            limit = self.accepted[run_id]
            if run.capacity is not None:
                limit = run.capacity if limit is None else min(limit, run.capacity)
            factor = (
                limit / total
                if limit is not None and total > limit and total > 0
                else 1
            )
            self.flows[run_id] = {
                k: v * factor for k, v in offered.items() if v * factor > 0
            }
            self.seen[run_id].update(k for k, v in offered.items() if v > 0)

    def arriving(self, node_id: str) -> Mix:
        mix: Mix = {}
        for run in self.into.get(node_id, ()):
            for key, rate in self.flows[run.id].items():
                _add(mix, key, rate)
        return mix

    def offer(self, node_id: str, mix: Mix) -> None:
        """Share each commodity of ``mix`` over the runs leaving the node, by what each accepts."""
        runs = self.out_of.get(node_id, [])
        for run in runs:
            for key in mix:
                self.offered[run.id].pop(key, None)
        if not runs:
            return
        accepts = tuple(
            self.accepted[r.id] if self.accepted[r.id] is not None else _unbounded(r)
            for r in runs
        )
        for key, rate in mix.items():
            for run, share in zip(runs, self.flow.share(rate, accepts), strict=True):
                _add(self.offered[run.id], key, share)

    def cell_round(self, cell_id: str) -> None:
        cell = self.netlist.cells[cell_id]
        pins = self.graph.pins_of_cell.get(cell_id, [])
        ins = [p for p in pins if p.direction == "in"]
        outs = [p for p in pins if p.direction == "out"]
        seen = {
            p.pin: frozenset().union(
                *(self.seen[r.id] for r in self.into.get(p.id, ()))
            )
            for p in ins
        }
        capacities = {
            p.pin: sum(
                (_capacity(r, self.accepted) for r in self.into.get(p.id, ())),
                Fraction(0),
            )
            for p in ins
        }
        room = {
            p.pin: sum(
                (_capacity(r, self.accepted) for r in self.out_of.get(p.id, ())),
                Fraction(0),
            )
            for p in outs
        }
        accepts = self.flow.accept(cell, seen, capacities, room)
        for p in ins:
            for run in self.into.get(p.id, ()):
                self.accepted[run.id] = accepts.get(p.pin, capacities[p.pin])
        inputs = {p.pin: self.arriving(p.id) for p in ins}
        made = self.flow.produce(cell, inputs, room)
        outputs: dict[str, Mix]
        if made is None:
            outputs = {p.pin: self.declared(p) for p in outs}
            total, load, note = None, None, ""
        else:
            outputs, total, load, note = (
                dict(made.outputs),
                made.made,
                made.load,
                made.note,
            )
        for p in outs:
            self.offer(p.id, outputs.get(p.pin, {}))
        if total is None:
            total = {}
            for mix in outputs.values():
                for key, rate in mix.items():
                    _add(total, key, rate)
        self.cells[cell_id] = CellFlow(
            cell_id, inputs, outputs, dict(total), load, note
        )

    def declared(self, node: Node) -> Mix:
        """A source pin's share of its net's declared rate, as one commodity."""
        for net in self.netlist.nets.values():
            for ref in net.sources:
                if ref.cell == node.cell and ref.pin == node.pin:
                    share = Fraction(net.rate) / len(net.sources)
                    return {self.commodity[node.id]: share} if share > 0 else {}
        return {}

    def unit_round(self, node: Node) -> None:
        ins = self.into.get(node.id, [])
        outs = self.out_of.get(node.id, [])
        outlet = sum((_capacity(r, self.accepted) for r in outs), Fraction(0))
        capacities = tuple(_capacity(r, None) for r in ins)
        for run, take in zip(
            ins, self.flow.merge_accept(capacities, outlet), strict=True
        ):
            self.accepted[run.id] = take
        unit = self.graph.layout.units.get(node.unit) if node.kind == "unit" else None
        mix = self.arriving(node.id)
        if unit is not None:
            mix = {k: v for k, v in mix.items() if self.flow.passes(unit, k)}
        self.offer(node.id, mix)

    # ----------------------------------------------------------- result
    def result(self, rounds: int, converged: bool) -> Evaluation:
        out = Evaluation(rounds=rounds, converged=converged)
        produced: dict[str, Fraction] = {}
        delivered: dict[str, Fraction] = {}
        for cell_id, state in self.cells.items():
            for pin, mix in state.outputs.items():
                produced[f"{cell_id}.{pin}"] = _total(mix)
            for pin, mix in state.received.items():
                delivered[f"{cell_id}.{pin}"] = _total(mix)
        findings: list = []
        nets: dict[str, Fraction] = {}
        for run_id, run in self.graph.runs.items():
            total = _total(self.flows[run_id])
            if run.net:
                nets[run.net] = max(nets.get(run.net, Fraction(0)), total)
            offered = _total(self.offered[run_id])
            if run.capacity is not None and offered > run.capacity:
                findings.append(capacity_finding(run_id, offered, run.capacity))
        for net in self.netlist.nets.values():
            for sink in net.sinks:
                cell = self.netlist.cells.get(sink.cell)
                want = self.flow.demand(cell, sink.pin) if cell is not None else None
                got = delivered.get(str(sink), Fraction(0))
                if want is not None and got < want:
                    findings.append(starved(str(sink), got, Fraction(want)))
        if not converged:
            findings.append(unstable(rounds))
        out.produced, out.delivered, out.nets = produced, delivered, nets
        out.findings = tuple(findings)
        out.runs = {
            run_id: RunFlow(
                run_id,
                run.net,
                run.cells,
                run.carrier,
                dict(self.flows[run_id]),
                _total(self.flows[run_id]),
                run.capacity,
                run.source,
                run.target,
            )
            for run_id, run in self.graph.runs.items()
        }
        out.cells = dict(self.cells)
        return out


OPPOSITE = {"N": "S", "S": "N", "E": "W", "W": "E"}


def _heading(a: XY, b: XY) -> str:
    """The side a step from ``a`` to ``b`` travels toward."""
    if b[0] == a[0]:
        return "S" if b[1] > a[1] else "N"
    return "E" if b[0] > a[0] else "W"


def _distances(roots: set[str], by_node: dict[str, list[Run]]) -> dict[str, int]:
    """Every node's distance in runs from the nearest root, breadth first."""
    distance = dict.fromkeys(roots, 0)
    frontier = sorted(roots)
    while frontier:
        here = frontier.pop(0)
        for run in by_node.get(here, ()):
            far = run.target if run.source == here else run.source
            if far not in distance:
                distance[far] = distance[here] + 1
                frontier.append(far)
    return distance


def _unbounded(run: Run) -> Fraction:
    return run.capacity if run.capacity is not None else Fraction(10**9)


def _capacity(run: Run, accepted: dict[str, Fraction | None] | None) -> Fraction:
    """What a run may carry now: its acceptance when known, else its carrier's capacity, else unbounded."""
    if accepted is not None and accepted.get(run.id) is not None:
        return accepted[run.id]
    return _unbounded(run)


__all__ = [
    "EPSILON",
    "MAX_ROUNDS",
    "SNAP",
    "SNAP_EVERY",
    "CellFlow",
    "Graph",
    "LayoutGraph",
    "Node",
    "Routed",
    "Run",
    "RunFlow",
]
