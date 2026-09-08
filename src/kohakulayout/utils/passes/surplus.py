"""Surplus sinks: a sink cell attached to every net whose rate exceeds its demand."""

from collections.abc import Mapping
from fractions import Fraction

from kohakulayout.ir import Footprint, Netlist, PinRef
from kohakulayout.utils.build import add_cells, add_footprint, cell, pin_for


def surplus(
    nl: Netlist,
    sink_footprint: Footprint,
    sink_kind: str | None,
    demand: Mapping[str, Fraction | int],
) -> Netlist:
    """For each net named in ``demand`` with rate above it, a ``<net>_surplus`` sink joins the net."""
    nl = add_footprint(nl, sink_footprint)
    kind = sink_kind or sink_footprint.id
    nets = dict(nl.nets)
    for net_id, wanted in demand.items():
        net = nets.get(net_id)
        if net is None or net.rate <= Fraction(wanted):
            continue
        sink_id = f"{net_id}_surplus"
        nl = add_cells(nl, [cell(sink_id, sink_footprint.id, kind=kind)])
        ref = PinRef(cell=sink_id, pin=pin_for(nl, sink_id, "in", net.carrier).id)
        nets[net_id] = net.model_copy(update={"sinks": (*net.sinks, ref)})
    return nl.model_copy(update={"nets": nets})


__all__ = ["surplus"]
