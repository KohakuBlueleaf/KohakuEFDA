"""Builders: a netlist without hand-wiring pins. Every function takes a netlist and returns a new one."""

from collections.abc import Iterable, Mapping, Sequence
from fractions import Fraction
from itertools import pairwise
from typing import Any

from kohakulayout.errors import IRError
from kohakulayout.ir import Cell, Constraint, Footprint, Net, Netlist, Pin, PinRef


def next_id(nl: Netlist, prefix: str) -> str:
    """``<prefix><n>`` for the smallest n not yet a cell, net or group id."""
    taken = set(nl.cells) | set(nl.nets) | set(nl.groups)
    n = 1
    while f"{prefix}{n}" in taken:
        n += 1
    return f"{prefix}{n}"


def pin_for(
    nl: Netlist, cell_id: str, direction: str, carrier: str | None = None
) -> Pin:
    """The cell's first pin in ``direction`` on ``carrier``; raises when it has none."""
    if cell_id not in nl.cells:
        raise IRError(f"no cell {cell_id!r}")
    for pin in nl.pins_of(cell_id):
        if pin.direction == direction and (carrier is None or pin.carrier == carrier):
            return pin
    raise IRError(f"{cell_id} has no {direction} pin on {carrier or 'any carrier'}")


def add_cells(nl: Netlist, cells: Iterable[Cell]) -> Netlist:
    merged = dict(nl.cells)
    for cell in cells:
        if cell.id in merged:
            raise IRError(f"cell {cell.id!r} exists")
        merged[cell.id] = cell
    return nl.model_copy(update={"cells": merged})


def add_footprint(nl: Netlist, footprint: Footprint) -> Netlist:
    if footprint.id in nl.library:
        return nl
    return nl.model_copy(update={"library": {**nl.library, footprint.id: footprint}})


def add_net(nl: Netlist, net: Net) -> Netlist:
    if net.id in nl.nets:
        raise IRError(f"net {net.id!r} exists")
    return nl.model_copy(update={"nets": {**nl.nets, net.id: net}})


def cell(id: str, footprint: str, **fields: Any) -> Cell:
    """A leaf cell whose kind is its footprint unless given, the way the text form builds one."""
    fields.setdefault("kind", footprint)
    return Cell(id=id, footprint=footprint, **fields)


def chain(
    nl: Netlist,
    cells: Sequence[str],
    carrier: str,
    rate: Fraction | int = 0,
    prefix: str = "n",
) -> Netlist:
    """One net between each consecutive pair: the first's out pin to the next's in pin."""
    for a, b in pairwise(cells):
        net = Net(
            id=next_id(nl, prefix),
            carrier=carrier,
            rate=Fraction(rate),
            sources=(PinRef(cell=a, pin=pin_for(nl, a, "out", carrier).id),),
            sinks=(PinRef(cell=b, pin=pin_for(nl, b, "in", carrier).id),),
        )
        nl = add_net(nl, net)
    return nl


def fanout(
    nl: Netlist,
    source: str,
    sinks: Sequence[str],
    carrier: str,
    rate: Fraction | int = 0,
    prefix: str = "n",
) -> Netlist:
    """One net from the source's out pin to every sink's in pin."""
    net = Net(
        id=next_id(nl, prefix),
        carrier=carrier,
        rate=Fraction(rate),
        sources=(PinRef(cell=source, pin=pin_for(nl, source, "out", carrier).id),),
        sinks=tuple(
            PinRef(cell=s, pin=pin_for(nl, s, "in", carrier).id) for s in sinks
        ),
    )
    return add_net(nl, net)


def bank(
    nl: Netlist,
    cells: Sequence[str],
    lane_in: str,
    lane_out: str,
    carrier: str,
    rate: Fraction | int = 0,
    prefix: str = "n",
) -> Netlist:
    """Cells fed by one lane from ``lane_in`` and emptying into one lane toward ``lane_out``."""
    nl = fanout(nl, lane_in, cells, carrier, rate, prefix)
    net = Net(
        id=next_id(nl, prefix),
        carrier=carrier,
        rate=Fraction(rate),
        sources=tuple(
            PinRef(cell=c, pin=pin_for(nl, c, "out", carrier).id) for c in cells
        ),
        sinks=(PinRef(cell=lane_out, pin=pin_for(nl, lane_out, "in", carrier).id),),
    )
    return add_net(nl, net)


def hub(
    nl: Netlist,
    id: str,
    footprint: Footprint,
    pins: Sequence[Pin] | None = None,
    constraint: Constraint | str = "free",
    **fields: Any,
) -> Netlist:
    """A many-pinned cell with its own constraint kind; the footprint joins the library."""
    nl = add_footprint(nl, footprint)
    kind = Constraint(kind=constraint) if isinstance(constraint, str) else constraint
    return add_cells(
        nl,
        [
            Cell(
                id=id,
                kind=footprint.id,
                footprint=footprint.id,
                pins=tuple(pins or ()),
                constraint=kind,
                **fields,
            )
        ],
    )


def entries(
    nl: Netlist,
    side: str,
    carrier: str,
    sinks: Sequence[str],
    rate: Fraction | int = 0,
    prefix: str = "n",
) -> Netlist:
    """A supply from the board's edge: a net with no source and ``outside`` set, feeding the sinks."""
    net = Net(
        id=next_id(nl, prefix),
        carrier=carrier,
        rate=Fraction(rate),
        sinks=tuple(
            PinRef(cell=s, pin=pin_for(nl, s, "in", carrier).id) for s in sinks
        ),
        outside=side,
    )
    return add_net(nl, net)


def instantiate(
    nl: Netlist,
    module: str,
    id: str,
    ports: Mapping[str, str] | None = None,
    **port_nets: str,
) -> Netlist:
    """An instance of a module or macro, each named port joined to a net by the port's direction."""
    bindings = {**(ports or {}), **port_nets}
    if module in nl.macros:
        cell_ = Cell(id=id, macro=module)
        module_id = nl.macros[module].module
    elif module in nl.modules:
        cell_ = Cell(id=id, module=module)
        module_id = module
    else:
        raise IRError(f"no module or macro {module!r}")
    declared = {p.id: p for p in nl.modules[module_id].ports}
    nl = add_cells(nl, [cell_])
    nets = dict(nl.nets)
    for port_id, net_id in bindings.items():
        port = declared.get(port_id)
        if port is None:
            raise IRError(f"{module} has no port {port_id!r}")
        ref = PinRef(cell=id, pin=port_id)
        net = nets.get(net_id) or Net(id=net_id, carrier=port.carrier)
        if port.direction == "out":
            net = net.model_copy(update={"sources": (*net.sources, ref)})
        else:
            net = net.model_copy(update={"sinks": (*net.sinks, ref)})
        nets[net_id] = net
    return nl.model_copy(update={"nets": nets})


__all__ = [
    "add_cells",
    "add_footprint",
    "add_net",
    "bank",
    "cell",
    "chain",
    "entries",
    "fanout",
    "hub",
    "instantiate",
    "next_id",
    "pin_for",
]
