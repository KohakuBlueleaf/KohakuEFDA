"""Lane packing: a net over its carrier's capacity split into lanes, first-fit decreasing over its sinks' shares."""

from fractions import Fraction

from kohakulayout.ir import Fabric, Net, Netlist, PinRef


def source_pins(nl: Netlist, net: Net) -> list[PinRef]:
    """Every out pin of the net's source cells on its carrier, the ones already on the net first."""
    pins: list[PinRef] = list(net.sources)
    for ref in net.sources:
        for pin in nl.pins_of(ref.cell):
            candidate = PinRef(cell=ref.cell, pin=pin.id)
            if (
                pin.direction == "out"
                and pin.carrier == net.carrier
                and candidate not in pins
            ):
                pins.append(candidate)
    return pins


def lane_nets(nl: Netlist, net: Net, capacity: Fraction) -> list[Net]:
    """The lanes for one net: equal sink shares packed first-fit, each lane on its own source pin.

    A pin sits on one net, so a source without a spare out pin per lane keeps the net whole
    and ``balance`` reports the capacity.
    """
    if not net.sinks or net.rate <= capacity or not net.sources:
        return [net]
    share = net.rate / len(net.sinks)
    bins: list[list] = []
    loads: list[Fraction] = []
    for sink in net.sinks:
        for index, load in enumerate(loads):
            if load + share <= capacity:
                bins[index].append(sink)
                loads[index] = load + share
                break
        else:
            bins.append([sink])
            loads.append(share)
    pins = source_pins(nl, net)
    if len(bins) == 1 or len(pins) < len(bins):
        return [net]
    return [
        net.model_copy(
            update={
                "id": f"{net.id}/{k + 1}",
                "sources": (pins[k],),
                "sinks": tuple(group),
                "rate": share * len(group),
            }
        )
        for k, group in enumerate(bins)
    ]


def lanes(nl: Netlist, fabric: Fabric) -> Netlist:
    """Every net whose rate exceeds its carrier's capacity becomes lane nets; the rest pass through."""
    nets: dict[str, Net] = {}
    for net in nl.nets.values():
        carrier = fabric.carriers.get(net.carrier)
        if carrier is None or carrier.capacity is None:
            nets[net.id] = net
            continue
        for lane in lane_nets(nl, net, carrier.capacity):
            nets[lane.id] = lane
    return nl.model_copy(update={"nets": nets})


__all__ = ["lane_nets", "lanes", "source_pins"]
