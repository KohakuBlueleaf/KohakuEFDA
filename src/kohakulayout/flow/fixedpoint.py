"""The greatest fixed point under the declared rates: prime every net with its rate, iterate downward until nothing moves.

Each round: what the sources make merges under the carrier's capacity, splits evenly over
the net's live sinks, and each cell's transfer turns delivered inputs into what its out pins
may make, never above the previous round. A loop keeps its declared rates unless a cell on it
makes less.
"""

from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

from kohakulayout.flow.findings import capacity as capacity_finding
from kohakulayout.flow.findings import loop as loop_finding
from kohakulayout.flow.findings import starved, unstable
from kohakulayout.ir import Netlist

MAX_ROUNDS = 200


@dataclass
class Evaluation:
    produced: dict[str, Fraction] = field(default_factory=dict)
    delivered: dict[str, Fraction] = field(default_factory=dict)
    nets: dict[str, Fraction] = field(default_factory=dict)
    loops: tuple[str, ...] = ()
    rounds: int = 0
    converged: bool = False
    findings: tuple = ()

    def at(self, cell: str, pin: str) -> Fraction:
        key = f"{cell}.{pin}"
        return self.delivered.get(key, self.produced.get(key, Fraction(0)))


def cycles(netlist: Netlist) -> tuple[str, ...]:
    """The nets on a cycle of the cell graph, found by Tarjan's strongly connected components."""
    succ: dict[str, list[tuple[str, str]]] = {c: [] for c in netlist.cells}
    for net in netlist.nets.values():
        for src in net.sources:
            for sink in net.sinks:
                succ.setdefault(src.cell, []).append((sink.cell, net.id))
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on: set[str] = set()
    comp: dict[str, int] = {}
    counter = [0]

    def visit(v: str) -> None:
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on.add(v)
        for w, _ in succ.get(v, ()):
            if w not in index:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            while True:
                w = stack.pop()
                on.discard(w)
                comp[w] = index[v]
                if w == v:
                    break

    for v in sorted(succ):
        if v not in index:
            visit(v)
    looped: set[str] = set()
    for v, edges in succ.items():
        for w, net_id in edges:
            if comp.get(v) == comp.get(w):
                looped.add(net_id)
    return tuple(sorted(looped))


class FixedPoint:
    id = "fixedpoint"

    def __init__(self, max_rounds: int = MAX_ROUNDS) -> None:
        self.max_rounds = max_rounds

    def evaluate(self, netlist: Netlist, flow: Any, fabric: Any = None) -> Evaluation:
        flat = netlist.flatten()
        out = Evaluation(loops=cycles(flat))
        produced: dict[str, Fraction] = {}
        for net in flat.nets.values():
            share = (
                Fraction(net.rate) / len(net.sources)
                if net.sources
                else Fraction(net.rate)
            )
            for src in net.sources:
                produced[str(src)] = share
        limits = (
            {k: c.capacity for k, c in fabric.carriers.items()}
            if fabric is not None
            else {}
        )
        capped: set[str] = set()
        findings: list = []
        delivered: dict[str, Fraction] = {}
        for rounds in range(1, self.max_rounds + 1):
            supplies: dict[str, Fraction] = {}
            delivered = {}
            for net in flat.nets.values():
                limit = limits.get(net.carrier)
                offered = (
                    tuple(produced[str(src)] for src in net.sources)
                    if net.sources
                    else (Fraction(net.rate),)
                )
                total = sum(offered, Fraction(0))
                if limit is not None and total > limit and net.id not in capped:
                    capped.add(net.id)
                    findings.append(capacity_finding(net.id, total, limit))
                accepted = flow.merge(offered, limit)
                supply = sum(accepted, Fraction(0))
                supplies[net.id] = supply
                live = [sink for sink in net.sinks if _live(flow, flat, sink)]
                shares = flow.split(supply, len(live))
                for sink, share in zip(live, shares, strict=True):
                    delivered[str(sink)] = share
                for sink in net.sinks:
                    delivered.setdefault(str(sink), Fraction(0))
            changed = False
            for cell_id, cell in flat.cells.items():
                inputs = {
                    p.id: delivered.get(f"{cell_id}.{p.id}", Fraction(0))
                    for p in flat.pins_of(cell_id)
                    if p.direction == "in"
                }
                made = flow.transfer(cell, inputs)
                if made is None:
                    continue
                for pin_id, rate in made.items():
                    key = f"{cell_id}.{pin_id}"
                    if key in produced and Fraction(rate) < produced[key]:
                        produced[key] = Fraction(rate)
                        changed = True
            out.rounds = rounds
            if not changed:
                out.converged = True
                break
        out.produced, out.delivered, out.nets = produced, delivered, supplies
        for net in flat.nets.values():
            for sink in net.sinks:
                want = flow.demand(flat.cells[sink.cell], sink.pin)
                got = delivered.get(str(sink), Fraction(0))
                if want is not None and got < want:
                    findings.append(starved(str(sink), got, Fraction(want)))
        if out.loops:
            findings.append(loop_finding(out.loops))
        if not out.converged:
            findings.append(unstable(out.rounds))
        out.findings = tuple(findings)
        return out


def _live(flow: Any, netlist: Netlist, sink: Any) -> bool:
    want = flow.demand(netlist.cells[sink.cell], sink.pin)
    return want is None or want > 0


__all__ = ["MAX_ROUNDS", "Evaluation", "FixedPoint", "cycles"]
