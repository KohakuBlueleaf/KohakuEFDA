"""Fan-out replication: buffer cells inserted, in a tree, so no net drives more sinks than the limit."""

from kohakulayout.ir import Footprint, Net, Netlist, PinRef
from kohakulayout.utils.build import add_cells, add_footprint, add_net, cell, pin_for


def replicate(
    nl: Netlist,
    max_fanout: int,
    buffer_footprint: Footprint,
    buffer_kind: str | None = None,
) -> Netlist:
    """Nets with more than ``max_fanout`` sinks get buffers; a buffer drives up to ``max_fanout`` sinks or buffers."""
    if max_fanout < 1:
        raise ValueError("max_fanout must be positive")
    nl = add_footprint(nl, buffer_footprint)
    kind = buffer_kind or buffer_footprint.id
    nets = dict(nl.nets)
    for net_id in sorted(nl.nets):
        net = nets[net_id]
        level = 0
        while len(net.sinks) > max_fanout:
            level += 1
            sinks = list(net.sinks)
            new_sinks: list[PinRef] = []
            for index in range(0, len(sinks), max_fanout):
                buffer_id = f"{net_id}_b{level}_{index // max_fanout + 1}"
                nl = add_cells(nl, [cell(buffer_id, buffer_footprint.id, kind=kind)])
                branch = Net(
                    id=f"{net_id}/{buffer_id}",
                    carrier=net.carrier,
                    rate=net.rate,
                    sources=(
                        PinRef(
                            cell=buffer_id,
                            pin=pin_for(nl, buffer_id, "out", net.carrier).id,
                        ),
                    ),
                    sinks=tuple(sinks[index : index + max_fanout]),
                )
                nl = add_net(nl, branch)
                nets[branch.id] = branch
                new_sinks.append(
                    PinRef(
                        cell=buffer_id, pin=pin_for(nl, buffer_id, "in", net.carrier).id
                    )
                )
            net = net.model_copy(update={"sinks": tuple(new_sinks)})
            nets[net_id] = net
    return nl.model_copy(update={"nets": nets})


__all__ = ["replicate"]
