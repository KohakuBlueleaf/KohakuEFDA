"""The framework netlist with the plan's repeat units as modules: one module per top-level tile
type, its body the cells and inner nets of the first copy, a port for every pin a net leaves
the copy through; one instance per copy; the nets between copies and the cells built once
rewritten onto the instances' ports. Flattened, it is the flat netlist again with the leaves
named ``<instance>/<leaf>``."""

import re
from typing import Any

from kohakuefda.model.cells import Netlist as ProjectNetlist
from kohakuefda.physics.fabric import NAMESPACE
from kohakuefda.plan.units import Shape, shape_of
from kohakulayout.ir import Cell, Net, Netlist, PinRef
from kohakulayout.ir import Layout as FrameworkLayout
from kohakulayout.ir.netlist import Module, ModulePort


class HierarchyError(ValueError):
    """The copies of a tile do not share one shape."""


def instance_id(unit: str) -> str:
    """A unit name (``<tile>#<copy>``) as a framework identifier."""
    return re.sub(r"\W", "_", unit)


def tile_of(unit: str) -> str:
    return unit.rsplit("#", 1)[0]


def copies_of(netlist: ProjectNetlist) -> dict[str, list[list[str]]]:
    """Per tile type its copies in order, each the ids of its cells in netlist order."""
    out: dict[str, dict[int, list[str]]] = {}
    for cell in netlist.cells:
        if cell.unit is None:
            continue
        tile, copy = cell.unit.rsplit("#", 1)
        out.setdefault(tile, {}).setdefault(int(copy), []).append(cell.id)
    return {tile: [copies[k] for k in sorted(copies)] for tile, copies in out.items()}


def shapes(netlist: ProjectNetlist, ids: list[str]) -> list[Shape]:
    cells = {c.id: c for c in netlist.cells}
    return [shape_of(cells[i]) for i in ids]


def paired(
    netlist: ProjectNetlist, first: list[str], other: list[str]
) -> dict[str, str]:
    """Each cell of ``other`` matched to the cell of ``first`` of the same shape, in order."""
    buckets: dict[Shape, list[str]] = {}
    for cell_id, shape in zip(first, shapes(netlist, first), strict=True):
        buckets.setdefault(shape, []).append(cell_id)
    out: dict[str, str] = {}
    for cell_id, shape in zip(other, shapes(netlist, other), strict=True):
        if not buckets.get(shape):
            raise HierarchyError(f"copy holding {cell_id} has no mate of shape {shape}")
        out[cell_id] = buckets[shape].pop(0)
    if any(buckets.values()):
        raise HierarchyError("a copy is short of the cells of the first")
    return out


def leaf_map(netlist: ProjectNetlist) -> dict[str, str]:
    """Every flattened leaf name (``<instance>/<first copy's cell>``) to the project cell it stands for."""
    out: dict[str, str] = {}
    for tile, runs in copies_of(netlist).items():
        for index, ids in enumerate(runs):
            inst = instance_id(f"{tile}#{index}")
            for cell_id, base in paired(netlist, runs[0], ids).items():
                out[f"{inst}/{base}"] = cell_id
    return out


def leaf_name(leaf: dict[str, tuple[str, str]], cell_id: str) -> str:
    """A project cell as the world will name it: its flattened leaf name, or itself when built once."""
    if cell_id in leaf:
        inst, base = leaf[cell_id]
        return f"{inst}/{base}"
    return cell_id


def rebased(attrs: dict[str, Any], leaf: dict[str, tuple[str, str]]) -> dict[str, Any]:
    """Net facts with every cell id renamed to the world's leaf name (lanes are ``cell:pin:cell:pin:rate``)."""
    facts = dict(attrs.get(NAMESPACE, {}))
    lanes = []
    for text in facts.get("lanes", ()):
        sc, sp, tc, tp, rate = str(text).split(":")
        lanes.append(f"{leaf_name(leaf, sc)}:{sp}:{leaf_name(leaf, tc)}:{tp}:{rate}")
    if lanes:
        facts["lanes"] = lanes
    return {**attrs, NAMESPACE: facts}


def hierarchical_of(netlist: ProjectNetlist, flat: Netlist) -> Netlist:
    """``flat`` (the synth's framework netlist) folded into modules and instances by the cells' units."""
    copies = copies_of(netlist)
    leaf: dict[str, tuple[str, str]] = {}
    for tile, runs in copies.items():
        for index, ids in enumerate(runs):
            mates = paired(netlist, runs[0], ids)
            for cell_id in ids:
                leaf[cell_id] = (instance_id(f"{tile}#{index}"), mates[cell_id])
    unit_of = {c: inst for c, (inst, _) in leaf.items()}
    modules: dict[str, Module] = {}
    ports: dict[str, dict[str, ModulePort]] = {tile: {} for tile in copies}
    inner: dict[str, dict[str, Net]] = {tile: {} for tile in copies}
    top_nets: dict[str, Net] = {}
    tiles = {c.id: tile_of(c.unit) for c in netlist.cells if c.unit is not None}

    def rewrite(ref: PinRef, direction: str, carrier: str) -> PinRef:
        if ref.cell not in leaf:
            return ref
        inst, base = leaf[ref.cell]
        port = f"{base}__{ref.pin}"
        ports[tiles[ref.cell]].setdefault(
            port,
            ModulePort(
                id=port,
                direction=direction,
                carrier=carrier,
                inner=PinRef(cell=base, pin=ref.pin),
            ),
        )
        return PinRef(cell=inst, pin=port)

    for net_id, net in flat.nets.items():
        refs = (*net.sources, *net.sinks)
        homes = {unit_of.get(r.cell) for r in refs}
        if len(homes) == 1 and None not in homes:
            first = refs[0].cell
            if leaf[first][0] == instance_id(f"{tiles[first]}#0"):
                inner[tiles[first]][net_id] = net.model_copy(
                    update={
                        "sources": tuple(
                            PinRef(cell=leaf[r.cell][1], pin=r.pin) for r in net.sources
                        ),
                        "sinks": tuple(
                            PinRef(cell=leaf[r.cell][1], pin=r.pin) for r in net.sinks
                        ),
                    }
                )
            continue
        top_nets[net_id] = net.model_copy(
            update={
                "sources": tuple(rewrite(r, "out", net.carrier) for r in net.sources),
                "sinks": tuple(rewrite(r, "in", net.carrier) for r in net.sinks),
                "attrs": rebased(dict(net.attrs), leaf),
            }
        )
    top_cells: dict[str, Cell] = {}
    for cell_id, cell in flat.cells.items():
        if cell_id not in leaf:
            top_cells[cell_id] = cell
    for tile, runs in copies.items():
        body = Netlist(
            pack=flat.pack,
            cells={c: flat.cells[c] for c in runs[0]},
            nets=inner[tile],
            groups={},
        )
        modules[instance_id(tile)] = Module(
            id=instance_id(tile), ports=tuple(ports[tile].values()), body=body
        )
        for index in range(len(runs)):
            inst = instance_id(f"{tile}#{index}")
            top_cells[inst] = Cell(id=inst, module=instance_id(tile))
    attrs = dict(flat.attrs)
    facts = dict(attrs.get(NAMESPACE, {}))
    facts["links"] = [
        ":".join(leaf_name(leaf, end) for end in str(text).split(":"))
        for text in facts.get("links", ())
    ]
    attrs[NAMESPACE] = facts
    return Netlist(
        pack=flat.pack,
        library=dict(flat.library),
        cells=top_cells,
        nets=top_nets,
        groups={
            k: g
            for k, g in flat.groups.items()
            if not any(m in leaf for m in g.members)
        },
        modules=modules,
        attrs=attrs,
    )


def project_layout(
    layout: FrameworkLayout, netlist: ProjectNetlist, flat: Netlist
) -> FrameworkLayout:
    """A layout of the hierarchical problem's world renamed onto the flat problem: every leaf
    placement under its project cell, every flattened inner wire under the flat net that
    joins the same project pins; a wire with no such net keeps its name and is left alone.
    """
    leaves = leaf_map(netlist)
    placements = {
        leaves.get(k, k): p.model_copy(update={"cell": leaves.get(k, k)})
        for k, p in layout.placements.items()
    }
    by_pins = {
        frozenset((r.cell, r.pin) for r in (*n.sources, *n.sinks)): net_id
        for net_id, n in flat.nets.items()
    }
    wires = {}
    for net_id, wire in layout.wires.items():
        pins = wire.ports.keys() if wire.ports else ()
        key = frozenset(
            (
                leaves.get(pin.rsplit(".", 1)[0], pin.rsplit(".", 1)[0]),
                pin.rsplit(".", 1)[1],
            )
            for pin in pins
        )
        target = by_pins.get(key, net_id) if key else net_id
        wires[target] = wire.model_copy(update={"net": target})
    return layout.model_copy(update={"placements": placements, "wires": wires})


__all__ = [
    "HierarchyError",
    "copies_of",
    "hierarchical_of",
    "instance_id",
    "leaf_map",
    "leaf_name",
    "paired",
    "project_layout",
    "rebased",
]
