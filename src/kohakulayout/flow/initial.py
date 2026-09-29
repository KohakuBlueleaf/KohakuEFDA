"""The first round of a routed evaluation: empty runs, or every net's declared flow."""

from fractions import Fraction
from typing import Any

MODES = ("empty", "declared")


def initial_flows(
    graph: Any, netlist: Any, flow: Any, mode: str
) -> dict[str, dict[str, Fraction]]:
    """The flow per run to start from: none when ``empty``; when ``declared``, each
    net's source demands (or its rate shared over its sources), capped by the run's
    capacity."""
    if mode == "empty":
        return {}

    by_net = {}
    for net in netlist.nets.values():
        mixture: dict[str, Fraction] = {}
        for source in net.sources:
            cell = netlist.cells[source.cell]
            demand = flow.demand(cell, source.pin)
            rate = (
                Fraction(net.rate or 0) / max(1, len(net.sources))
                if demand is None
                else Fraction(demand)
            )
            if rate > 0:
                commodity = flow.commodity(cell, source.pin)
                mixture[commodity] = mixture.get(commodity, Fraction(0)) + rate
        by_net[net.id] = mixture

    out = {}
    for key, run in graph.runs.items():
        mixture = by_net.get(run.net, {})
        total = sum(mixture.values(), Fraction(0))
        if not total:
            continue
        scale = Fraction(1)
        if run.capacity is not None:
            scale = min(scale, run.capacity / total)
        out[key] = {item: rate * scale for item, rate in mixture.items()}
    return out


__all__ = ["MODES", "initial_flows"]
