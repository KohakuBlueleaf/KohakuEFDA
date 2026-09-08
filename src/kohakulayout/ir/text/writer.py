"""Levels to canonical text: sorted ids, fixed option order, moves for wires when the problem is known."""

from fractions import Fraction
from typing import Any

from kohakulayout._rust_bridge import rust_write_kl
from kohakulayout.ir.assessment import Assessment
from kohakulayout.ir.base import Level
from kohakulayout.ir.fabric import Fabric, Region
from kohakulayout.ir.layout import Layout, Wire
from kohakulayout.ir.netlist import Cell, Macro, Module, Net, Netlist, Pin, PinRef
from kohakulayout.ir.problem import Problem
from kohakulayout.ir.text.moves import moves_from_cells
from kohakulayout.ir.text.values import quote, write_loose_value, write_value

INDENT = "    "


def _opt(key: str, value: Any) -> str:
    return f"{key}={write_value(value)}"


def _attrs(attrs: dict[str, dict[str, Any]]) -> list[str]:
    return [
        f"+{ns}.{key}={write_loose_value(value)}"
        for ns in sorted(attrs)
        for key, value in sorted(attrs[ns].items())
    ]


def _rate(value: Fraction) -> str:
    return (
        str(value.numerator)
        if value.denominator == 1
        else f"{value.numerator}/{value.denominator}"
    )


# ------------------------------------------------------------------ fabric


def _region_line(region: Region, fabric: Fabric) -> str:
    every = fabric.width * fabric.height
    if len(region.cells()) == every:
        body = "all"
    else:
        body = " ".join(f"rect {r.x},{r.y} {r.w}x{r.h}" for r in region.rects)
    return " ".join(["region", region.id, body, *_attrs(region.attrs)])


def fabric_lines(fabric: Fabric) -> list[str]:
    parts = [
        "fabric",
        f"{fabric.width}x{fabric.height}",
        _opt("layers", list(fabric.layers)),
    ]
    if fabric.entries:
        parts.append(_opt("entries", list(fabric.entries)))
    lines = [" ".join([*parts, *_attrs(fabric.attrs)])]
    for rid in sorted(fabric.regions):
        lines.append(_region_line(fabric.regions[rid], fabric))
    for cid in sorted(fabric.carriers):
        carrier = fabric.carriers[cid]
        parts = ["carrier", carrier.id, carrier.layer]
        if carrier.capacity is not None:
            parts.append(_rate(carrier.capacity))
        lines.append(" ".join([*parts, *_attrs(carrier.attrs)]))
    return lines


# ----------------------------------------------------------------- netlist


def _port_line(port: Any) -> str:
    head = f"{port.id} {port.direction} {port.carrier} {port.side}{port.offset}"
    return " ".join([head, *_attrs(port.attrs)])


def _lib_lines(netlist: Netlist, indent: str) -> list[str]:
    lines = []
    for fid in sorted(netlist.library):
        fp = netlist.library[fid]
        parts = ["lib", fp.id, f"{fp.width}x{fp.height}"]
        if fp.layer != "ground":
            parts.append(_opt("layer", fp.layer))
        if fp.occludes:
            parts.append(_opt("occludes", list(fp.occludes)))
        if tuple(fp.rotations) != (0, 90, 180, 270):
            parts.append(_opt("rot", list(fp.rotations)))
        parts += _attrs(fp.attrs)
        ports = [_port_line(p) for p in fp.ports]
        if len(ports) <= 4:
            lines.append(
                f"{indent}{' '.join(parts)} {{ {' ; '.join(ports)} }}"
                if ports
                else f"{indent}{' '.join(parts)} {{ }}"
            )
        else:
            lines.append(f"{indent}{' '.join(parts)} {{")
            lines += [f"{indent}{INDENT}{p}" for p in ports]
            lines.append(f"{indent}}}")
    return lines


def _cell_line(cell: Cell, pack: str) -> str:
    ref = cell.footprint or cell.module or cell.macro or ""
    parts = ["cell", cell.id, ref]
    if cell.kind and cell.kind != ref:
        parts.append(_opt("kind", cell.kind))
    if cell.label:
        parts.append(_opt("label", cell.label))
    constraint = cell.constraint
    if constraint.kind != "free" or constraint.attrs:
        parts.append(_opt("at", constraint.kind))
        for ns in sorted(constraint.attrs):
            for key, value in sorted(constraint.attrs[ns].items()):
                parts.append(
                    _opt(key if ns == (pack or "pack") else f"at.{ns}.{key}", value)
                )
    if cell.group:
        parts.append(_opt("group", cell.group))
    if cell.needs:
        parts.append(_opt("needs", list(cell.needs)))
    parts += _attrs(cell.attrs)
    return " ".join(parts)


def _default_pins(netlist: Netlist, cell: Cell) -> tuple[Pin, ...]:
    return netlist.model_copy(
        update={
            "cells": {**netlist.cells, cell.id: cell.model_copy(update={"pins": ()})}
        }
    ).pins_of(cell.id)


def _pin_lines(netlist: Netlist, cell: Cell) -> list[str]:
    if not cell.pins or cell.pins == _default_pins(netlist, cell):
        return []
    return [
        f"pin {cell.id}.{p.id} {p.direction} {p.carrier} {_opt('ports', '|'.join(p.ports))}"
        for p in cell.pins
    ]


def _net_line(net: Net) -> str:
    parts = ["net", net.id, net.carrier]
    if net.rate:
        parts.append(_rate(net.rate))
    if net.kind:
        parts.append(_opt("kind", net.kind))
    if net.label:
        parts.append(_opt("label", net.label))
    if net.outside is not None:
        parts.append(_opt("outside", net.outside))
    parts += _attrs(net.attrs)
    parts.append(":")
    parts += [str(r) for r in net.sources]
    parts.append("->")
    parts += [str(r) for r in net.sinks]
    return " ".join(parts)


def _macro_lines(macro: Macro, indent: str) -> list[str]:
    lines = [f"{indent}macro {macro.id} {macro.module} {{"]
    lines += [
        f"{indent}{INDENT}{line}"
        for line in layout_lines(macro.layout, None, header=False)
    ]
    lines.append(f"{indent}}}")
    return lines


def _module_lines(module: Module, pack: str, indent: str) -> list[str]:
    lines = [f"{indent}module {module.id} {{"]
    for port in module.ports:
        lines.append(
            f"{indent}{INDENT}port {port.id} {port.direction} {port.carrier} = {port.inner}"
        )
    lines += scope_lines(module.body, pack, indent + INDENT)
    lines.append(f"{indent}}}")
    return lines


def scope_lines(netlist: Netlist, pack: str, indent: str = "") -> list[str]:
    lines = (
        [indent + " ".join(["attrs", *_attrs(netlist.attrs)])] if netlist.attrs else []
    )
    lines += _lib_lines(netlist, indent)
    for mid in sorted(netlist.modules):
        lines += _module_lines(netlist.modules[mid], pack, indent)
    for mid in sorted(netlist.macros):
        lines += _macro_lines(netlist.macros[mid], indent)
    for cid in sorted(netlist.cells):
        cell = netlist.cells[cid]
        lines.append(indent + _cell_line(cell, pack))
        lines += [indent + line for line in _pin_lines(netlist, cell)]
    for nid in sorted(netlist.nets):
        lines.append(indent + _net_line(netlist.nets[nid]))
    for gid in sorted(netlist.groups):
        group = netlist.groups[gid]
        parts = ["group", group.id]
        if group.kind:
            parts.append(_opt("kind", group.kind))
        parts += _attrs(group.attrs)
        lines.append(indent + " ".join([*parts, ":", *group.members]))
    return lines


# ------------------------------------------------------------------ layout


def _endpoint(cell_xy: tuple[int, int], pins: dict[tuple[int, int], PinRef]) -> str:
    ref = pins.get(cell_xy)
    return str(ref) if ref is not None else f"@{cell_xy[0]},{cell_xy[1]}"


def _wire_line(wire: Wire, layout: Layout, netlist: Netlist | None) -> str:
    net = netlist.nets.get(wire.net) if netlist is not None else None
    parts = ["wire", wire.net]
    attach: dict[tuple[int, int], PinRef] = {}
    if net is None or netlist is None:
        first = wire.segments[0] if wire.segments else None
        if first is not None:
            parts += [_opt("carrier", first.carrier), _opt("layer", first.layer)]
    else:
        for ref in net.sources + net.sinks:
            xy = layout.attach(netlist, ref)
            if xy is not None and xy not in attach:
                attach[xy] = ref
    if wire.units:
        parts.append(_opt("units", list(wire.units)))
    segments = []
    for segment in wire.segments:
        cells = segment.cells
        if net is None or netlist is None:
            body = (
                "cells " + " ".join(f"{x},{y}" for x, y in cells[:-1])
                if len(cells) > 1
                else "cells " + f"{cells[0][0]},{cells[0][1]}"
            )
            segments.append(f"{body} -> @{cells[-1][0]},{cells[-1][1]}")
        else:
            start = _endpoint(cells[0], attach)
            moves = moves_from_cells(cells)
            end = _endpoint(cells[-1], attach)
            segments.append(" ".join([start, *moves, "->", end]))
    return " ".join([*parts, ":", " ; ".join(segments)])


def layout_lines(
    layout: Layout, netlist: Netlist | None, header: bool = True
) -> list[str]:
    flat_netlist = netlist.flatten() if netlist is not None else None
    head = " ".join(p for p in ["layout", layout.problem, *_attrs(layout.attrs)] if p)
    lines = [head] if header else []
    for cid in sorted(layout.placements):
        p = layout.placements[cid]
        lines.append(f"place {p.cell} {p.x},{p.y} r{p.rot}")
    for cid in sorted(layout.instances):
        p = layout.instances[cid]
        lines.append(f"instance {p.cell} {p.x},{p.y} r{p.rot}")
    for nid in sorted(layout.wires):
        lines.append(_wire_line(layout.wires[nid], layout, flat_netlist))
    for uid in sorted(layout.units):
        unit = layout.units[uid]
        parts = [
            "unit",
            unit.id,
            unit.footprint,
            f"{unit.x},{unit.y}",
            f"r{unit.rot}",
            _opt("owner", unit.owner),
        ]
        if unit.kind and unit.kind != unit.footprint:
            parts.append(_opt("kind", unit.kind))
        parts += _attrs(unit.attrs)
        lines.append(" ".join(parts))
    for reservation in layout.reservations:
        parts = ["reserve", reservation.tag, reservation.layer]
        if reservation.carrier:
            parts.append(_opt("carrier", reservation.carrier))
        rects = Region.of("r", frozenset(reservation.cells)).rects
        lines.append(
            " ".join([*parts, ":", *[f"rect {r.x},{r.y} {r.w}x{r.h}" for r in rects]])
        )
    return lines


# -------------------------------------------------------------- assessment


def assessment_lines(assessment: Assessment) -> list[str]:
    lines = [f"assessment {assessment.layout}".rstrip()]
    for name in sorted(assessment.metrics):
        lines.append(f"metric {name} {write_value(assessment.metrics[name])}")
    for finding in assessment.findings:
        parts = [
            "finding",
            finding.rule,
            finding.severity,
            finding.subject,
            quote(finding.message),
            *_attrs(finding.attrs),
        ]
        lines.append(" ".join(parts))
    lines.append(f"complete {'true' if assessment.complete else 'false'}")
    lines.append(f"valid {'true' if assessment.valid else 'false'}")
    return lines


# ----------------------------------------------------------------- entry


def write(level: Level, context: Any = None) -> str:
    """The canonical text of ``level``; a layout gets pin endpoints when ``context`` holds the netlist."""
    context_json = None
    if isinstance(context, Problem | Netlist):
        context_json = context.to_json()
    elif context is not None and getattr(context, "problem", None) is not None:
        context_json = context.problem.to_json()
    elif context is not None and getattr(context, "netlist", None) is not None:
        context_json = context.netlist.to_json()
    native = rust_write_kl(level.to_json(), context_json)
    if native is not None:
        return native
    lines = ["kl 1"]
    if isinstance(level, Problem):
        if level.physics:
            lines.append(f"physics {level.physics}")
        lines += fabric_lines(level.fabric)
        for key in sorted(level.params):
            lines.append(f"param {key}={write_loose_value(level.params[key])}")
        lines += scope_lines(
            level.netlist,
            level.physics.split("@")[0] if level.physics else level.netlist.pack,
        )
    elif isinstance(level, Netlist):
        if level.pack:
            lines.append(f"physics {level.pack}")
        lines += scope_lines(level, level.pack)
    elif isinstance(level, Layout):
        netlist = getattr(context, "netlist", None) if context is not None else None
        if isinstance(context, Problem):
            netlist = context.netlist
        lines += layout_lines(level, netlist)
    elif isinstance(level, Assessment):
        lines += assessment_lines(level)
    else:
        raise TypeError(f"no text form for {type(level).__name__}")
    return "\n".join(lines) + "\n"
