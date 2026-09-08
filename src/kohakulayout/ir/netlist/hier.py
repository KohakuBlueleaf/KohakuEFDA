"""Hierarchy in L3: modules with ports and no geometry, macros with a fixed internal layout.

A macro's footprint is derived from its fragment: the bounding box of the leaves and the
ports that reach the box's edge. ``derive_footprint`` is what the parser and the check use.
"""

from typing import TYPE_CHECKING

from kohakulayout.ir.base import Model
from kohakulayout.ir.geometry import XY, attach_cell, footprint_cells
from kohakulayout.ir.layout import Layout
from kohakulayout.ir.netlist.model import Direction, Footprint, PinRef, Port

if TYPE_CHECKING:
    from kohakulayout.ir.netlist import Netlist


class ModulePort(Model):
    id: str
    direction: Direction
    carrier: str
    inner: PinRef


class Module(Model):
    id: str
    ports: tuple[ModulePort, ...] = ()
    body: "Netlist"


class Macro(Model):
    id: str
    module: str
    layout: Layout
    footprint: Footprint | None = None


def _fragment_cells(macro: Macro, footprints: dict[str, Footprint]) -> frozenset[XY]:
    cells: set[XY] = set()
    for placement in macro.layout.placements.values():
        fp = footprints.get(placement.cell)
        if fp is None:
            continue
        cells.update(
            footprint_cells(
                placement.x, placement.y, fp.width, fp.height, placement.rot
            )
        )
    for wire in macro.layout.wires.values():
        for segment in wire.segments:
            cells.update(segment.cells)
    for unit in macro.layout.units.values():
        cells.add((unit.x, unit.y))
    return frozenset(cells)


def derive_footprint(
    macro: Macro,
    module: Module,
    footprints: dict[str, Footprint],
    pins: dict[str, dict[str, tuple[str, ...]]],
) -> tuple[Footprint | None, list[str]]:
    """The macro's footprint from its fragment, or the problems that prevent one.

    ``footprints`` maps each placed leaf to its footprint; ``pins`` maps each leaf to its
    pin id to the ports that pin may use. A module port becomes a macro port at the attach
    cell of its inner pin's first allowed port, which must lie just outside the box.
    """
    cells = _fragment_cells(macro, footprints)
    problems: list[str] = []
    where = f"macro {macro.id}"
    if not cells:
        return None, [f"{where}: the fragment places nothing"]
    min_x = min(c[0] for c in cells)
    min_y = min(c[1] for c in cells)
    if (min_x, min_y) != (0, 0):
        problems.append(
            f"{where}: the fragment's top-left corner is ({min_x},{min_y}), not (0,0)"
        )
    width = max(c[0] for c in cells) + 1
    height = max(c[1] for c in cells) + 1
    ports: list[Port] = []
    layers: set[str] = set()
    for placement in macro.layout.placements.values():
        fp = footprints.get(placement.cell)
        if fp is not None:
            layers.add(fp.layer)
            layers.update(fp.occludes)
    for mport in module.ports:
        placement = macro.layout.placements.get(mport.inner.cell)
        fp = footprints.get(mport.inner.cell)
        allowed = pins.get(mport.inner.cell, {}).get(mport.inner.pin, ())
        if placement is None or fp is None or not allowed:
            problems.append(
                f"{where}: port {mport.id!r} binds to an unplaced or unknown pin {mport.inner}"
            )
            continue
        port = fp.port(allowed[0])
        if port is None:
            problems.append(
                f"{where}: port {mport.id!r} names a missing port {allowed[0]!r}"
            )
            continue
        ax, ay = attach_cell(fp.width, fp.height, port.side, port.offset, placement.rot)
        ax, ay = ax + placement.x, ay + placement.y
        if ay == -1 and 0 <= ax < width:
            side, offset = "N", ax
        elif ay == height and 0 <= ax < width:
            side, offset = "S", ax
        elif ax == -1 and 0 <= ay < height:
            side, offset = "W", ay
        elif ax == width and 0 <= ay < height:
            side, offset = "E", ay
        else:
            problems.append(
                f"{where}: port {mport.id!r} does not reach the macro's edge"
            )
            continue
        ports.append(
            Port(
                id=mport.id,
                side=side,
                offset=offset,
                direction=mport.direction,
                carrier=mport.carrier,
            )
        )
    if problems:
        return None, problems
    layer = "ground" if "ground" in layers or not layers else min(layers)
    occludes = tuple(sorted(layers - {layer}))
    return (
        Footprint(
            id=macro.id,
            width=width,
            height=height,
            layer=layer,
            occludes=occludes,
            ports=tuple(ports),
        ),
        [],
    )
