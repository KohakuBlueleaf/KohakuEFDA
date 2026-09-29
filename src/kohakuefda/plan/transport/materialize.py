"""Materialise an exact allocation as compatible pins and independent physical lanes."""

from collections import defaultdict

from kohakuefda.model.cells import Netlist, NetSpec, Pin, PinRef, PortRef
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.plan import Finding
from kohakuefda.plan.operating import packed_rates
from kohakuefda.plan.transport.domains import allowed_ports, match_ports
from kohakuefda.plan.transport.model import TransportError, TransportResult, fingerprint


def materialize(dataset: Dataset, netlist: Netlist, result: TransportResult) -> Netlist:
    """Replace solid nets with independently routed lanes on their original compatible ports."""
    if not result.feasible:
        raise TransportError(result.reason or "no verified transport allocation")
    if result.source_digest != fingerprint(netlist):
        raise TransportError("the allocation belongs to a different source netlist")
    original_cells = {cell.id: cell for cell in netlist.cells}
    original_nets = {net.id: net for net in netlist.nets}
    lanes = [
        (f"direct_{index}_{lane}", transfer, rate)
        for index, transfer in enumerate(result.transfers)
        for lane, rate in enumerate(
            packed_rates(transfer.rate, dataset.constants.belt_per_min)
        )
    ]
    endpoints = defaultdict(list)
    for key, transfer, rate in lanes:
        item = original_nets[transfer.net].item_id
        for direction, cell_id in (("out", transfer.source), ("in", transfer.sink)):
            ports = allowed_ports(dataset, original_cells[cell_id], item, direction)
            endpoints[cell_id, direction].append((key, ports))
    selected = {}
    for (cell_id, direction), entries in endpoints.items():
        assignment = match_ports(
            [tuple(p.index for p in ports) for _, ports in entries]
        )
        for (key, ports), port_index in zip(entries, assignment, strict=True):
            selected[key, direction] = (
                next(p for p in ports if p.index == port_index),
                ports,
            )
    out = netlist.model_copy(deep=True)
    cells = {cell.id: cell for cell in out.cells}
    replaced = {transfer.net for transfer in result.transfers}
    old_pins = {
        (ref.cell_id, ref.pin_id)
        for net in out.nets
        if net.id in replaced
        for ref in [*net.sources, *net.sinks]
    }
    touched = {cell_id for cell_id, _ in old_pins}
    for cell in out.cells:
        cell.pins = [p for p in cell.pins if (cell.id, p.id) not in old_pins]
        if cell.id in touched:
            cell.unit = None
    out.nets = [net for net in out.nets if net.id not in replaced]
    for key, transfer, rate in lanes:
        spec = original_nets[transfer.net]
        ends = {}
        for direction, cell_id in (("out", transfer.source), ("in", transfer.sink)):
            port, ports = selected[key, direction]
            pin = Pin(
                id=f"{direction}:{key}",
                direction=direction,
                kind="belt",
                item_id=spec.item_id,
                rate=rate,
                cell=(port.x, port.y),
                edge=port.edge,
                alternatives=[
                    PortRef(index=p.index, cell=(p.x, p.y), edge=p.edge) for p in ports
                ],
                net=key,
            )
            cells[cell_id].pins.append(pin)
            ends[direction] = PinRef(cell_id=cell_id, pin_id=pin.id, rate=rate)
        out.nets.append(
            NetSpec(
                id=f"{spec.id}_{key}",
                item_id=spec.item_id,
                kind="belt",
                rate=rate,
                nominal=rate,
                trunk_lanes=1,
                sources=[ends["out"]],
                sinks=[ends["in"]],
                via_depot_ok=spec.via_depot_ok,
            )
        )
    out.findings.append(
        Finding(
            rule="transport.direct",
            severity="info",
            subject="transport",
            message=f"{result.lanes} direct belt lanes; exact balances and compatible physical ports checked; routed throughput still requires verification",
        )
    )
    return out


__all__ = ["materialize"]
