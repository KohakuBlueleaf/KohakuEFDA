"""The wires of a framework layout as flows: the net's graph, its orientation and the flow on every step.

A wire is a set of segments the router laid: each runs from the tree to the pin it
reached, in no flow order of its own. The pack's lane facts say what each pin supplies
or takes; on a tree every step is directed from the side that supplies more than it
takes, elsewhere a segment ending on a source's attach cell flows the other way. The
supply is pushed along that orientation, split evenly where the net branches and
summed where it joins, and the translation reads the result to orient every piece and
to decide what each junction is.
"""

from fractions import Fraction
from itertools import pairwise
from typing import Any

from kohakuefda.model.layout import Cell as XY
from kohakuefda.physics.facts import lane_facts
from kohakuefda.physics.library import BRIDGE, CONVERGER, SPLITTER

SPLITTERS = frozenset(SPLITTER.values())
CONVERGERS = frozenset(CONVERGER.values())
BRIDGES = frozenset(BRIDGE.values())


def step_between(a: XY, b: XY) -> tuple[int, int]:
    return (b[0] - a[0], b[1] - a[1])


class Flows:
    """The wire analysis the translation reads: graph, potential, flows, junctions and orientation."""

    def graph(self, net_id: str) -> dict[XY, set[XY]]:
        """The net's cells with their neighbours along its segments."""
        out: dict[XY, set[XY]] = {}
        wire = self.layout.wires.get(net_id)
        for segment in wire.segments if wire is not None else ():
            for cell in segment.cells:
                out.setdefault(cell, set())
            for a, b in pairwise(segment.cells):
                out[a].add(b)
                out[b].add(a)
        return out

    def orientation(self, net_id: str) -> set[tuple[XY, XY]]:
        """Every step of the net directed: on a tree with rates, each step away from the side whose share of the supply passes its share of the demand (``tree_orientation``); elsewhere the way the router laid it: along each segment, and against a segment that ends on a source's attach cell no sink shares and no other segment starts from (a join, stored from the tree to the source; a lane ending where another lane leaves a source merges into it); kept per net, the layout never changes under a translation."""
        memo = self.__dict__.setdefault("_orientation", {})
        if net_id in memo:
            return memo[net_id]
        net = self.kl.nets[net_id]
        sources = {
            self.attach[(r.cell, r.pin)]
            for r in net.sources
            if (r.cell, r.pin) in self.attach
        }
        sinks = {
            self.attach[(r.cell, r.pin)]
            for r in net.sinks
            if (r.cell, r.pin) in self.attach
        }
        wire = self.layout.wires.get(net_id)
        heads = {seg.cells[0] for seg in wire.segments} if wire is not None else set()
        out: set[tuple[XY, XY]] = set()
        for segment in wire.segments if wire is not None else ():
            cells = list(segment.cells)
            joins = cells[-1] in heads and cells[-1] != cells[0]
            tree_ward = cells[-1] in sources and cells[-1] not in sinks and not joins
            if len(cells) > 1 and tree_ward:
                cells.reverse()
            out.update(pairwise(cells))
        out = self.tree_orientation(net_id, out) or out
        memo[net_id] = out
        return out

    def rates(
        self, net_id: str, graph: dict[XY, set[XY]]
    ) -> tuple[dict[XY, Fraction], dict[XY, Fraction]]:
        """The supply at each source's attach cell and the demand at each sink's, from the net's lane facts, over the cells the wire has."""
        supply: dict[XY, Fraction] = {}
        demand: dict[XY, Fraction] = {}
        for source, sink, rate in lane_facts(self.kl.nets[net_id]):
            start = self.attach.get(source)
            goal = self.attach.get(sink)
            if start in graph:
                supply[start] = supply.get(start, Fraction(0)) + rate
            if goal in graph:
                demand[goal] = demand.get(goal, Fraction(0)) + rate
        return supply, demand

    def tree_orientation(
        self, net_id: str, laid: set[tuple[XY, XY]]
    ) -> set[tuple[XY, XY]] | None:
        """The steps of a tree net each directed from the side whose share of the supply passes its share of the demand, a step both sides balance as laid; ``None`` for a net that is no tree, has no rates or attaches on a crossing."""
        graph = self.graph(net_id)
        crossings = self.crossings(net_id)
        edges = sum(len(others) for others in graph.values()) // 2
        if not edges or edges != len(graph) + len(crossings) - 1:
            return None
        supply, demand = self.rates(net_id, graph)
        total_supply = sum(supply.values(), Fraction(0))
        total_demand = sum(demand.values(), Fraction(0))
        if not total_supply or not total_demand:
            return None
        if crossings & (set(supply) | set(demand)):
            return None
        Node = tuple[XY, int | None]

        def node(cell: XY, a: XY, b: XY) -> Node:
            return (cell, int(a[0] == b[0])) if cell in crossings else (cell, None)

        adjacency: dict[Node, set[Node]] = {}
        for a, others in graph.items():
            for b in others:
                adjacency.setdefault(node(a, a, b), set()).add(node(b, a, b))
        root = min(adjacency)
        order = [root]
        parent: dict[Node, Node | None] = {root: None}
        for here in order:
            for other in sorted(adjacency[here]):
                if other not in parent:
                    parent[other] = here
                    order.append(other)
        if len(order) != len(adjacency):
            return None
        beyond_supply = {n: supply.get(n[0], Fraction(0)) for n in order}
        beyond_demand = {n: demand.get(n[0], Fraction(0)) for n in order}
        out: set[tuple[XY, XY]] = set()
        for here in reversed(order):
            above = parent[here]
            if above is None:
                continue
            beyond_supply[above] += beyond_supply[here]
            beyond_demand[above] += beyond_demand[here]
            surplus = (
                beyond_supply[here] * total_demand - beyond_demand[here] * total_supply
            )
            a, b = above[0], here[0]
            if surplus > 0 or (surplus == 0 and (b, a) in laid):
                out.add((b, a))
            else:
                out.add((a, b))
        return out

    def crossings(self, net_id: str) -> frozenset[XY]:
        """The net's cells where two of its own lanes cross on a bridge: one node per axis."""
        graph = self.graph(net_id)
        bridges = self.bridges_of.get(self.kl.nets[net_id].carrier, set())
        return frozenset(xy for xy in bridges if len(graph.get(xy, ())) == 4)

    def flows(self, net_id: str) -> dict[tuple[XY, XY], Fraction]:
        """The rate each directed step carries: on a tree, each pin's supply pushed along the orientation, a sink taking its demand as it passes, a branch sharing what arrives evenly; elsewhere every lane's rate along its path."""
        graph = self.graph(net_id)
        net = self.kl.nets[net_id]
        crossings = self.crossings(net_id)
        supply, demand = self.rates(net_id, graph)
        edges = sum(len(others) for others in graph.values()) // 2
        if not graph or edges != len(graph) + len(crossings) - 1:
            return self.lane_flows(graph, net, crossings)
        directed = self.orientation(net_id)

        def node(cell: XY, a: XY, b: XY) -> tuple[XY, int | None]:
            return (cell, int(a[0] == b[0])) if cell in crossings else (cell, None)

        ahead: dict[tuple[XY, int | None], list[tuple[XY, int | None]]] = {}
        waiting: dict[tuple[XY, int | None], int] = {}
        for a, b in directed:
            head = node(b, a, b)
            ahead.setdefault(node(a, a, b), []).append(head)
            waiting[head] = waiting.get(head, 0) + 1
        nodes = [(c, None) for c in graph if c not in crossings]
        nodes += [(c, axis) for c in sorted(crossings) for axis in (0, 1)]
        ready = [n for n in nodes if waiting.get(n, 0) == 0]
        carried: dict[tuple[XY, int | None], Fraction] = {}
        out: dict[tuple[XY, XY], Fraction] = {}
        while ready:
            here = ready.pop()
            cell = here[0]
            have = carried.get(here, Fraction(0)) + supply.get(cell, Fraction(0))
            have = max(have - demand.get(cell, Fraction(0)), Fraction(0))
            onward = sorted(ahead.get(here, ()))
            for other in onward:
                out[(cell, other[0])] = have / len(onward)
                carried[other] = carried.get(other, Fraction(0)) + have / len(onward)
                waiting[other] -= 1
                if waiting[other] == 0:
                    ready.append(other)
        if len(out) != len(directed):
            return self.lane_flows(graph, net, crossings)
        return out

    def lane_flows(
        self, graph: dict[XY, set[XY]], net: Any, crossings: frozenset[XY] = frozenset()
    ) -> dict[tuple[XY, XY], Fraction]:
        """Every lane's rate along its path from source to sink; the reading for a net that is not a tree."""
        out: dict[tuple[XY, XY], Fraction] = {}
        for source, sink, rate in lane_facts(net):
            start = self.attach.get(source)
            goal = self.attach.get(sink)
            if start is None or goal is None or start not in graph or goal not in graph:
                continue
            for a, b in pairwise(self.path(graph, start, goal, crossings)):
                out[(a, b)] = out.get((a, b), Fraction(0)) + rate
        return out

    @staticmethod
    def path(
        graph: dict[XY, set[XY]],
        start: XY,
        goal: XY,
        crossings: frozenset[XY] = frozenset(),
    ) -> list[XY]:
        """The cells from ``start`` to ``goal`` along the net, breadth first, straight through each of ``crossings``; empty when none joins them."""
        State = tuple[XY, XY | None]
        parent: dict[State, State | None] = {(start, None): None}
        frontier: list[State] = [(start, None)]
        found: State | None = (start, None) if start == goal else None
        while frontier and found is None:
            cell, came = frontier.pop(0)
            onward = sorted(graph[cell])
            if cell in crossings and came is not None:
                ahead = (2 * cell[0] - came[0], 2 * cell[1] - came[1])
                onward = [ahead] if ahead in graph[cell] else []
            for other in onward:
                state = (other, cell)
                if state not in parent:
                    parent[state] = (cell, came)
                    frontier.append(state)
                    if other == goal:
                        found = state
                        break
        if found is None:
            return []
        cells: list[XY] = []
        state: State | None = found
        while state is not None:
            cells.append(state[0])
            state = parent[state]
        return list(reversed(cells))

    def junction(
        self, net_id: str, xy: XY
    ) -> tuple[str | None, tuple[int, int] | None, tuple[int, int] | None]:
        """What a unit cell of the net must be by the steps meeting there: a splitter, a converger, or nothing; it faces the steps that carry the most."""
        graph = self.graph(net_id)
        directed = self.orientation(net_id)
        flows = self.flows(net_id)
        net = self.kl.nets[net_id]
        entering = sorted(
            (c for c in graph.get(xy, ()) if (c, xy) in directed),
            key=lambda c: (-flows.get((c, xy), Fraction(0)), c),
        )
        leaving = sorted(
            (c for c in graph.get(xy, ()) if (xy, c) in directed),
            key=lambda c: (-flows.get((xy, c), Fraction(0)), c),
        )
        came = step_between(entering[0], xy) if entering else None
        goes = step_between(xy, leaving[0]) if leaving else None
        arrivals = len(entering)
        departures = len(leaving)
        for ref in net.sources:
            if self.attach.get((ref.cell, ref.pin)) == xy:
                came = self.port_at(xy, "out") or came
                arrivals += 1
        for ref in net.sinks:
            if self.attach.get((ref.cell, ref.pin)) == xy:
                goes = self.port_at(xy, "in") or goes
                departures += 1
        unit = next(
            (
                u
                for u in self.layout.units.values()
                if (u.x, u.y) == xy and u.owner == f"net:{net_id}"
            ),
            None,
        )
        placed = (
            None
            if unit is None
            else ("split" if unit.footprint in SPLITTERS else "merge")
        )
        if not directed or (arrivals <= 1 and departures <= 1):
            return placed, came, goes
        return ("merge" if arrivals > 1 else "split"), came, goes

    def interior_terminals(self, net_id: str) -> set[XY]:
        """Attach cells of the net's pins that a segment runs through rather than ends at: flows meet there."""
        wire = self.layout.wires.get(net_id)
        if wire is None:
            return set()
        ends = {s.cells[0] for s in wire.segments} | {
            s.cells[-1] for s in wire.segments
        }
        interior = {c for s in wire.segments for c in s.cells[1:-1]}
        terminals = {
            self.attach[(r.cell, r.pin)]
            for r in self.kl.nets[net_id].pins()
            if (r.cell, r.pin) in self.attach
        }
        return (terminals & interior) - ends

    def junction_cells(self, net_id: str) -> set[XY]:
        return set(self.units_of.get(net_id, ())) | self.interior_terminals(net_id)

    def cuts_of(self, net_id: str, carrier: str) -> set[XY]:
        """The cells a piece stops at: the net's junctions that need a unit, and every bridge of its carrier."""
        junctions = {
            xy
            for xy in self.junction_cells(net_id)
            if self.junction(net_id, xy)[0] is not None
        }
        return junctions | self.bridges_of.get(carrier, set())

    def oriented(self, net_id: str) -> list[list[XY]]:
        """The net's live pieces between its units, each in flow order; a junction no unit needs joins its two pieces; a piece another piece covers whole (a seat at a cell the tree already holds) is dropped."""
        net = self.kl.nets[net_id]
        junctions = self.junction_cells(net_id)
        cuts = junctions | self.bridges_of.get(net.carrier, set())
        directed = self.orientation(net_id)
        flows = self.flows(net_id)
        pieces: list[list[XY]] = []
        wire = self.layout.wires.get(net_id)
        for segment in wire.segments if wire is not None else ():
            for piece in self.pieces(list(segment.cells), cuts):
                if len(piece) > 1:
                    forward = sum(
                        (flows.get((a, b), Fraction(0)) for a, b in pairwise(piece)),
                        Fraction(0),
                    )
                    backward = sum(
                        (flows.get((b, a), Fraction(0)) for a, b in pairwise(piece)),
                        Fraction(0),
                    )
                    reverse = (
                        backward > forward
                        if forward != backward
                        else (piece[1], piece[0]) in directed
                    )
                    if reverse:
                        piece = list(reversed(piece))
                pieces.append(piece)
        for xy in sorted(junctions):
            if self.junction(net_id, xy)[0] is not None:
                continue
            tail = next((p for p in pieces if flows.get((p[-1], xy), 0) > 0), None)
            head = next((p for p in pieces if flows.get((xy, p[0]), 0) > 0), None)
            if tail is None and head is None:
                continue
            joined = (tail or []) + [xy] + (head or [])
            pieces = [p for p in pieces if p is not tail and p is not head]
            pieces.append(joined)
        return [
            p
            for i, p in enumerate(pieces)
            if not any(
                j != i and set(p) <= set(q) and len(q) > len(p)
                for j, q in enumerate(pieces)
            )
        ]

    def travel(self, net_id: str) -> dict[XY, tuple[int, int]]:
        """The direction the flow leaves each cell by: along the pieces, and into a sink's port."""
        out: dict[XY, tuple[int, int]] = {}
        for cells in self.oriented(net_id):
            for a, b in pairwise(cells):
                out.setdefault(a, step_between(a, b))
        for ref in self.kl.nets[net_id].sinks:
            attach = self.attach.get((ref.cell, ref.pin))
            step = self.port_at(attach, "in") if attach else None
            if attach is not None and step is not None:
                out.setdefault(attach, step)
        return out

    def arrival(self, net_id: str) -> dict[XY, tuple[int, int]]:
        """The direction the flow enters each cell by: along the pieces, and out of a source's port."""
        out: dict[XY, tuple[int, int]] = {}
        for cells in self.oriented(net_id):
            for a, b in pairwise(cells):
                out.setdefault(b, step_between(a, b))
        for ref in self.kl.nets[net_id].sources:
            attach = self.attach.get((ref.cell, ref.pin))
            step = self.port_at(attach, "out") if attach else None
            if attach is not None and step is not None:
                out.setdefault(attach, step)
        return out


__all__ = ["BRIDGES", "CONVERGERS", "SPLITTERS", "Flows", "step_between"]
