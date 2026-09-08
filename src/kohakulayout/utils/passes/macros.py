"""Macro formation: groups of cells become a module, a macro with a row fragment, and one instance each."""

from collections.abc import Callable
from typing import Any

from kohakulayout.errors import IRError
from kohakulayout.ir import (
    Cell,
    Layout,
    Macro,
    Module,
    ModulePort,
    Net,
    Netlist,
    PinRef,
    Placement,
)
from kohakulayout.ir.geometry import attach_cell, rotate_size
from kohakulayout.ir.netlist.hier import derive_footprint

Partition = Callable[..., list[list[str]]]


def bank_partition(nl: Netlist, **opts: Any) -> list[list[str]]:
    """Cells of one footprint that share every net they touch, two or more at a time."""
    signature: dict[tuple, list[str]] = {}
    touched: dict[str, set[str]] = {c: set() for c in nl.cells}
    for net in nl.nets.values():
        for ref in net.pins():
            if ref.cell in touched:
                touched[ref.cell].add(net.id)
    for cell_id, cell in sorted(nl.cells.items()):
        if cell.footprint is None or cell.is_instance or cell.constraint.kind != "free":
            continue
        key = (cell.footprint, frozenset(touched[cell_id]))
        signature.setdefault(key, []).append(cell_id)
    return [
        members
        for members in signature.values()
        if len(members) >= 2 and members and touched[members[0]]
    ]


def group_partition(nl: Netlist, **opts: Any) -> list[list[str]]:
    return [list(g.members) for g in nl.groups.values() if len(g.members) >= 2]


def custom_partition(
    nl: Netlist, partition: Partition | None = None, **opts: Any
) -> list[list[str]]:
    if partition is None:
        raise IRError("the custom strategy needs a partition callable")
    return [list(group) for group in partition(nl, **opts)]


MACROS: dict[str, Partition] = {
    "bank": bank_partition,
    "group": group_partition,
    "custom": custom_partition,
}


def _outer_pins(nl: Netlist, members: set[str]) -> list[tuple[str, str, str, str]]:
    """(cell, pin, direction, carrier) for member pins on nets that leave the group."""
    out: list[tuple[str, str, str, str]] = []
    seen: set[tuple[str, str]] = set()
    for net in nl.nets.values():
        cells = {r.cell for r in net.pins()}
        if cells <= members and net.outside is None:
            continue
        for ref in net.pins():
            if ref.cell in members and (ref.cell, ref.pin) not in seen:
                pin = nl.pin(ref)
                if pin is not None:
                    seen.add((ref.cell, ref.pin))
                    out.append((ref.cell, ref.pin, pin.direction, pin.carrier))
    return out


def _row(
    nl: Netlist, members: list[str], outer: list[tuple[str, str, str, str]], gap: int
) -> tuple[dict[str, Placement], int]:
    """Members side by side, rotated so every outer pin reaches the row's north or south edge."""
    fp = nl.footprint_for(members[0])
    for rot in fp.rotations:
        w, h = rotate_size(fp.width, fp.height, rot)
        fits = True
        for cell_id, pin_id, _, _ in outer:
            port = fp.port(nl.pin(PinRef(cell=cell_id, pin=pin_id)).ports[0])
            ax, ay = attach_cell(fp.width, fp.height, port.side, port.offset, rot)
            if not (ay == -1 or ay == h) or not (0 <= ax < w):
                fits = False
                break
        if fits:
            return {
                c: Placement(cell=c, x=i * (w + gap), y=0, rot=rot)
                for i, c in enumerate(members)
            }, rot
    raise IRError(
        f"no rotation puts every outer pin of {members[0]}'s footprint on the row's edge"
    )


def form(
    nl: Netlist, members: list[str], name: str, instance: str, gap: int = 1
) -> Netlist:
    """One module, one macro and one instance for ``members``; nets crossing the boundary rebind to the instance."""
    member_set = set(members)
    if len({nl.cells[c].footprint for c in members}) != 1:
        raise IRError(f"{name}: members must share one footprint")
    outer = _outer_pins(nl, member_set)
    ports = tuple(
        ModulePort(id=f"{c}_{p}", direction=d, carrier=k, inner=PinRef(cell=c, pin=p))
        for c, p, d, k in outer
    )
    inner_nets = {
        k: n
        for k, n in nl.nets.items()
        if {r.cell for r in n.pins()} <= member_set and n.outside is None
    }
    body = Netlist(
        pack=nl.pack,
        cells={c: nl.cells[c].model_copy(update={"group": None}) for c in members},
        nets=inner_nets,
    )
    module = Module(id=name, ports=ports, body=body)
    placements, _ = _row(nl, members, outer, gap)
    macro = Macro(id=f"{name}_row", module=name, layout=Layout(placements=placements))
    footprints = {c: nl.footprint_for(c) for c in members}
    pins = {c: {p.id: p.ports for p in nl.pins_of(c)} for c in members}
    footprint, problems = derive_footprint(macro, module, footprints, pins)
    if problems:
        raise IRError("; ".join(problems))
    macro = macro.model_copy(update={"footprint": footprint})
    cells = {k: v for k, v in nl.cells.items() if k not in member_set}
    cells[instance] = Cell(id=instance, macro=macro.id)
    rename = {(c, p): f"{c}_{p}" for c, p, _, _ in outer}
    nets: dict[str, Net] = {}
    for key, net in nl.nets.items():
        if key in inner_nets:
            continue
        sources = tuple(
            (
                PinRef(cell=instance, pin=rename[(r.cell, r.pin)])
                if (r.cell, r.pin) in rename
                else r
            )
            for r in net.sources
        )
        sinks = tuple(
            (
                PinRef(cell=instance, pin=rename[(r.cell, r.pin)])
                if (r.cell, r.pin) in rename
                else r
            )
            for r in net.sinks
        )
        nets[key] = net.model_copy(update={"sources": sources, "sinks": sinks})
    groups = {k: g for k, g in nl.groups.items() if not set(g.members) & member_set}
    return nl.model_copy(
        update={
            "cells": cells,
            "nets": nets,
            "groups": groups,
            "modules": {**nl.modules, name: module},
            "macros": {**nl.macros, macro.id: macro},
        }
    )


def macros(
    nl: Netlist, strategy: str = "bank", gap: int = 1, prefix: str = "M", **opts: Any
) -> Netlist:
    """Every group the strategy finds becomes a module, a macro and an instance; the result verifies."""
    partition = MACROS.get(strategy)
    if partition is None:
        raise IRError(f"no macro strategy {strategy!r}; known: {sorted(MACROS)}")
    for k, members in enumerate(partition(nl, **opts), start=1):
        nl = form(nl, list(members), f"{prefix}{k}", f"{prefix.lower()}{k}", gap)
    nl.verify()
    return nl


__all__ = [
    "MACROS",
    "Partition",
    "bank_partition",
    "custom_partition",
    "form",
    "group_partition",
    "macros",
]
