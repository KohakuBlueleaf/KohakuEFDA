"""The ASCII picture of a layout: one grid per layer, for tests and logs. Output only."""

from kohakulayout.ir.fabric import Fabric
from kohakulayout.ir.geometry import OUTWARD, XY, footprint_cells
from kohakulayout.ir.layout import Layout
from kohakulayout.ir.netlist import Footprint, Netlist

EMPTY = "."
WIRE_CHARS = {
    frozenset(): "·",
    frozenset("N"): "╵",
    frozenset("S"): "╷",
    frozenset("E"): "╶",
    frozenset("W"): "╴",
    frozenset("NS"): "│",
    frozenset("EW"): "─",
    frozenset("NE"): "└",
    frozenset("NW"): "┘",
    frozenset("SE"): "┌",
    frozenset("SW"): "┐",
    frozenset("NSE"): "├",
    frozenset("NSW"): "┤",
    frozenset("EWS"): "┬",
    frozenset("EWN"): "┴",
    frozenset("NSEW"): "┼",
}


def _letter(kind: str, upper: bool) -> str:
    ch = (kind or "#")[0]
    return ch.upper() if upper else ch.lower()


def dump(
    layout: Layout,
    netlist: Netlist | None = None,
    fabric: Fabric | None = None,
    unit_footprints: dict[str, Footprint] | None = None,
) -> str:
    """Footprints as their kind's first letter, wires as box lines by layer, units in lower case."""
    flat_netlist = netlist.flatten() if netlist is not None else None
    if fabric is not None:
        width, height, layers = fabric.width, fabric.height, list(fabric.layers)
    else:
        anchors = [(p.x, p.y) for p in layout.placements.values()]
        anchors += [(u.x, u.y) for u in layout.units.values()]
        anchors += [xy for w in layout.wires.values() for xy in w.cells()]
        if flat_netlist is not None:
            min_x, min_y, ext_w, ext_h = layout.extent(flat_netlist)
            anchors.append((min_x + ext_w - 1, min_y + ext_h - 1))
        width = max((x for x, _ in anchors), default=0) + 1
        height = max((y for _, y in anchors), default=0) + 1
        layers = sorted(
            {s.layer for w in layout.wires.values() for s in w.segments} | {"ground"}
        )
    grids: dict[str, list[list[str]]] = {
        layer: [[EMPTY] * width for _ in range(height)] for layer in layers
    }

    def put(layer: str, xy: XY, ch: str) -> None:
        x, y = xy
        if layer in grids and 0 <= x < width and 0 <= y < height:
            grids[layer][y][x] = ch

    for key, placement in layout.placements.items():
        fp = flat_netlist.footprint_for(key) if flat_netlist else None
        cell = flat_netlist.cells.get(key) if flat_netlist else None
        if fp is None:
            put("ground", (placement.x, placement.y), "#")
            continue
        letter = _letter(cell.kind if cell else fp.id, True)
        for layer in (fp.layer, *fp.occludes):
            for xy in footprint_cells(
                placement.x, placement.y, fp.width, fp.height, placement.rot
            ):
                put(layer, xy, letter)
    for wire in layout.wires.values():
        for segment in wire.segments:
            cells = set(segment.cells)
            for x, y in segment.cells:
                dirs = frozenset(
                    side
                    for side, (dx, dy) in OUTWARD.items()
                    if (x + dx, y + dy) in cells
                )
                put(segment.layer, (x, y), WIRE_CHARS.get(dirs, "┼"))
    for unit in layout.units.values():
        fp = (unit_footprints or {}).get(unit.footprint) or (
            netlist.library.get(unit.footprint) if netlist else None
        )
        letter = _letter(unit.kind or unit.footprint, False)
        if fp is None:
            put(layers[0], (unit.x, unit.y), letter)
            continue
        for layer in (fp.layer, *fp.occludes):
            for xy in footprint_cells(unit.x, unit.y, fp.width, fp.height, unit.rot):
                put(layer, xy, letter)
    blocks = []
    for layer in layers:
        rows = ["".join(row) for row in grids[layer]]
        border = "+" + "-" * width + "+"
        blocks.append(
            "\n".join([f"layer {layer}", border, *[f"|{row}|" for row in rows], border])
        )
    return "\n\n".join(blocks) + "\n"
