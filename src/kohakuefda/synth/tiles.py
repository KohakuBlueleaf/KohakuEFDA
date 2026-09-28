"""A unit as its own small problem, and its solved layout as a macro.

The module of a top-level tile becomes a problem on a box of its own, a one-cell ring around
it for the ports' attach cells that no wire may enter: the body's cells and
inner nets, the Endfield physics, and the cells that own a module port pinned to the box's rim with the port facing out (``rim``):
belt inputs on the north edge and belt outputs on the south, a pipe port on the side the
machine has it, so a rim cell takes all its inputs from outside the unit; the extraction cuts tiles at
machines fed from both inside and outside for that reason. A solved box, moved to the origin, is the
module's ``Macro`` with its footprint derived from the fragment, and the hierarchical netlist
with its instances on macros is what the rows place as items.
"""

from typing import Any

from kohakuefda.physics import EndfieldPhysics
from kohakuefda.physics.boundaries import RIM
from kohakuefda.physics.fabric import FIXED, NAMESPACE, RING
from kohakuefda.synth.footprints import ENTRY
from kohakulayout.ir import Cell, Constraint, Netlist, Problem
from kohakulayout.ir import Layout as FrameworkLayout
from kohakulayout.ir.geometry import footprint_cells
from kohakulayout.ir.netlist import Macro, derive_footprint

RING_WIDTH = 1
SIDE_OF = {"in": "N", "out": "S"}


class TileError(ValueError):
    """A unit's problem or macro cannot be formed."""


def port_sides(hier: Netlist, module_id: str) -> dict[str, str]:
    """Each module port's rim side: the side its pin's first port faces on the unrotated
    machine, north for belt inputs and south for belt outputs, a pipe where the machine
    has it."""
    module = hier.modules[module_id]
    out: dict[str, str] = {}
    for port in module.ports:
        cell = module.body.cells[port.inner.cell]
        fp = hier.library.get(cell.footprint or "")
        pin = next(
            (p for p in module.body.pins_of(port.inner.cell) if p.id == port.inner.pin),
            None,
        )
        found = (
            fp.port(pin.ports[0])
            if fp is not None and pin is not None and pin.ports
            else None
        )
        out[port.id] = found.side if found is not None else SIDE_OF[port.direction]
    return out


def tile_problem(hier: Netlist, module_id: str, box: tuple[int, int]) -> Problem:
    """The module's body on a ``box`` of its own, its port cells pinned to the rim; power is
    the whole layout's concern, so no cell needs it here."""
    module = hier.modules[module_id]
    sides = port_sides(hier, module_id)
    rims: dict[str, list[str]] = {}
    for port in module.ports:
        rims.setdefault(port.inner.cell, []).append(
            f"{sides[port.id]}:{port.inner.pin}"
        )
    cells: dict[str, Cell] = {}
    for cell_id, cell in module.body.cells.items():
        update: dict[str, Any] = {"needs": ()}
        if cell_id in rims:
            attrs = dict(cell.attrs)
            attrs[NAMESPACE] = {
                **attrs.get(NAMESPACE, {}),
                "rims": sorted(rims[cell_id]),
            }
            update |= {"constraint": Constraint(kind=RIM), "attrs": attrs}
        cells[cell_id] = cell.model_copy(update=update)
    physics = EndfieldPhysics()
    width, height = box
    params: dict[str, Any] = {
        "square": [width, height],
        "ring": RING_WIDTH,
        "entry_area": [RING_WIDTH, RING_WIDTH, RING_WIDTH + width, RING_WIDTH + height],
    }
    facts = dict(hier.attrs.get(NAMESPACE, {}))
    links = [
        text
        for text in facts.get("links", ())
        if all(end in cells for end in str(text).split(":"))
    ]
    netlist = Netlist(
        pack=hier.pack,
        library=dict(hier.library),
        cells=cells,
        nets=dict(module.body.nets),
        groups={},
        attrs={NAMESPACE: {**facts, "entry": ENTRY, "links": links}},
    )
    fabric = physics.fabric(params)
    regions = dict(fabric.regions)
    ring = regions.pop(RING, None)
    if ring is not None:
        regions[FIXED] = ring.model_copy(update={"id": FIXED})
    fabric = fabric.model_copy(update={"regions": regions})
    return Problem(physics=physics.ref, fabric=fabric, netlist=netlist, params=params)


def fragment_cells(problem: Problem, layout: FrameworkLayout) -> set[tuple[int, int]]:
    out: set[tuple[int, int]] = set()
    for placement in layout.placements.values():
        fp = problem.netlist.footprint_for(placement.cell)
        if fp is not None:
            out.update(
                footprint_cells(
                    placement.x, placement.y, fp.width, fp.height, placement.rot
                )
            )
    for wire in layout.wires.values():
        for segment in wire.segments:
            out.update(segment.cells)
    for unit in layout.units.values():
        out.add((unit.x, unit.y))
    return out


def normalised(problem: Problem, layout: FrameworkLayout) -> FrameworkLayout:
    """The layout moved so the fragment's top-left corner is the origin."""
    cells = fragment_cells(problem, layout)
    if not cells:
        return layout
    dx, dy = min(c[0] for c in cells), min(c[1] for c in cells)
    placements = {
        k: p.model_copy(update={"x": p.x - dx, "y": p.y - dy})
        for k, p in layout.placements.items()
    }
    wires = {
        k: w.model_copy(
            update={
                "segments": tuple(
                    s.model_copy(
                        update={"cells": tuple((x - dx, y - dy) for x, y in s.cells)}
                    )
                    for s in w.segments
                )
            }
        )
        for k, w in layout.wires.items()
    }
    units = {
        k: u.model_copy(update={"x": u.x - dx, "y": u.y - dy})
        for k, u in layout.units.items()
    }
    return layout.model_copy(
        update={"placements": placements, "wires": wires, "units": units}
    )


def macro_of(
    hier: Netlist, module_id: str, problem: Problem, layout: FrameworkLayout
) -> Macro:
    """The module's macro from a solved tile: the fragment at the origin with its derived footprint."""
    module = hier.modules[module_id]
    fragment = normalised(problem, layout)
    macro = Macro(id=f"{module_id}_macro", module=module_id, layout=fragment)
    footprints = {
        cell_id: problem.netlist.footprint_for(cell_id)
        for cell_id in fragment.placements
    }
    pins = {
        cell_id: {p.id: tuple(p.ports) for p in problem.netlist.pins_of(cell_id)}
        for cell_id in fragment.placements
    }
    footprint, problems = derive_footprint(macro, module, footprints, pins)
    if footprint is None or problems:
        raise TileError("; ".join(problems) or f"{module_id}: no footprint")
    return macro.model_copy(update={"footprint": footprint})


def with_macros(hier: Netlist, macros: dict[str, Macro]) -> Netlist:
    """The hierarchical netlist with every instance of a module that has a macro placed on it."""
    cells = {
        k: (
            c.model_copy(update={"module": None, "macro": macros[c.module].id})
            if c.module in macros
            else c
        )
        for k, c in hier.cells.items()
    }
    return hier.model_copy(
        update={"cells": cells, "macros": {m.id: m for m in macros.values()}}
    )


__all__ = [
    "RING_WIDTH",
    "TileError",
    "fragment_cells",
    "macro_of",
    "normalised",
    "port_sides",
    "tile_problem",
    "with_macros",
]
