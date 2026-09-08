"""The wires of a framework layout as flows: the net's graph, its potential and the flow on every step.

A wire is a set of cells; the pack's lane facts say which pins feed it and which drain
it. The flows follow the potential from the sources to the sinks, split where the net
branches and merge where it joins; the translation reads them to orient every piece and
to decide what each junction is.
"""

from fractions import Fraction
from itertools import pairwise

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

    def distances(self, net_id: str, ends: list[XY]) -> dict[XY, int]:
        """Steps along the net from each cell to the nearest of ``ends``; a cell none reaches is unmarked."""
        graph = self.graph(net_id)
        starts = [c for c in ends if c in graph]
        out = dict.fromkeys(starts, 0)
        frontier = list(starts)
        while frontier:
            cell = frontier.pop(0)
            for other in graph[cell]:
                if other not in out:
                    out[other] = out[cell] + 1
                    frontier.append(other)
        return out

    def potential(self, net_id: str) -> dict[XY, int]:
        """Flow runs uphill: a cell's distance from the sources less its distance to the sinks."""
        net = self.kl.nets[net_id]
        from_source = self.distances(
            net_id,
            [
                self.attach[(r.cell, r.pin)]
                for r in net.sources
                if (r.cell, r.pin) in self.attach
            ],
        )
        to_sink = self.distances(
            net_id,
            [
                self.attach[(r.cell, r.pin)]
                for r in net.sinks
                if (r.cell, r.pin) in self.attach
            ],
        )
        far = 10**6
        return {
            cell: from_source.get(cell, far) - to_sink.get(cell, far)
            for cell in self.graph(net_id)
        }

    def flows(self, net_id: str) -> dict[tuple[XY, XY], Fraction]:
        """The rate each directed step of the net carries: every lane's rate along its path from source to sink."""
        graph = self.graph(net_id)
        net = self.kl.nets[net_id]
        out: dict[tuple[XY, XY], Fraction] = {}
        for source, sink, rate in lane_facts(net):
            start = self.attach.get(source)
            goal = self.attach.get(sink)
            if start is None or goal is None or start not in graph or goal not in graph:
                continue
            for a, b in pairwise(self.path(graph, start, goal)):
                out[(a, b)] = out.get((a, b), Fraction(0)) + rate
        return out

    @staticmethod
    def path(graph: dict[XY, set[XY]], start: XY, goal: XY) -> list[XY]:
        """The cells from ``start`` to ``goal`` along the net, breadth first; empty when none joins them."""
        parent: dict[XY, XY | None] = {start: None}
        frontier = [start]
        while frontier and goal not in parent:
            cell = frontier.pop(0)
            for other in graph[cell]:
                if other not in parent:
                    parent[other] = cell
                    frontier.append(other)
        if goal not in parent:
            return []
        cells = [goal]
        while parent[cells[-1]] is not None:
            cells.append(parent[cells[-1]])
        return list(reversed(cells))

    def junction(
        self, net_id: str, xy: XY
    ) -> tuple[str | None, tuple[int, int] | None, tuple[int, int] | None]:
        """What a unit cell of the net must be by the flows meeting there: a splitter, a converger, or nothing."""
        graph = self.graph(net_id)
        flows = self.flows(net_id)
        net = self.kl.nets[net_id]
        ins = {c: flows.get((c, xy), Fraction(0)) for c in graph.get(xy, ())}
        outs = {c: flows.get((xy, c), Fraction(0)) for c in graph.get(xy, ())}
        came = goes = None
        entering = [c for c, r in ins.items() if r > 0]
        leaving = [c for c, r in outs.items() if r > 0]
        if entering:
            came = step_between(max(entering, key=lambda c: ins[c]), xy)
        if leaving:
            goes = step_between(xy, max(leaving, key=lambda c: outs[c]))
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
        if not flows or (arrivals <= 1 and departures <= 1):
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
        """The net's live pieces between its units, each in flow order; a junction no unit needs joins its two pieces."""
        net = self.kl.nets[net_id]
        junctions = self.junction_cells(net_id)
        cuts = junctions | self.bridges_of.get(net.carrier, set())
        potential = self.potential(net_id)
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
                    if flows and forward == backward == 0:
                        continue
                    reverse = (
                        backward > forward
                        if forward != backward
                        else potential[piece[0]] > potential[piece[-1]]
                    )
                    if reverse:
                        piece = list(reversed(piece))
                elif flows and not self.touches_flow(piece[0], flows):
                    continue
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
        return pieces

    @staticmethod
    def touches_flow(cell: XY, flows: dict[tuple[XY, XY], Fraction]) -> bool:
        return any(cell in edge and rate > 0 for edge, rate in flows.items())

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
