"""Text rendering of a layout: one character per cell, layers folded together."""

import logging

from kohakuefda.layout.geometry import machine_footprint, unit_footprint
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.layout import Layout

log = logging.getLogger(__name__)
HEADING_GLYPH = {"E": ">", "W": "<", "S": "v", "N": "^"}
UNIT_GLYPH = {
    "belt_router": "S",
    "pipe_router": "s",
    "belt_bridge": "+",
    "pipe_bridge": "x",
    "belt_control": "F",
    "pipe_control": "f",
}


def _arrow(a: tuple[int, int], b: tuple[int, int]) -> str:
    dx, dy = b[0] - a[0], b[1] - a[1]
    return {(1, 0): ">", (-1, 0): "<", (0, 1): "v", (0, -1): "^"}.get((dx, dy), "?")


def render_text(dataset: Dataset, layout: Layout) -> str:
    """Machines as letters (first of the name), belts as arrows, pipes as '=' or '|', units as
    glyphs, outside inputs as '@'."""
    log.debug(
        "rendering text grid %dx%d: %d machine(s), %d segment(s)",
        layout.width,
        layout.height,
        len(layout.machines),
        len(layout.segments),
    )
    grid = [["." for _ in range(layout.width)] for _ in range(layout.height)]

    def put(cell: tuple[int, int], glyph: str) -> None:
        x, y = cell
        if 0 <= x < layout.width and 0 <= y < layout.height:
            grid[y][x] = glyph

    for placed in layout.machines:
        letter = dataset.machines[placed.machine_id].names.en[:1].upper() or "#"
        for cell in machine_footprint(dataset, placed):
            put(cell, letter)
    for segment in layout.segments:
        cells = segment.cells
        for i, cell in enumerate(cells):
            nxt = cells[i + 1] if i + 1 < len(cells) else None
            if segment.kind == "belt":
                if nxt:
                    put(cell, _arrow(cell, nxt))
                else:
                    put(cell, HEADING_GLYPH.get(segment.heading, "*"))
            else:
                put(cell, "=" if nxt and nxt[1] == cell[1] else "|")
    for unit in layout.units:
        glyph = UNIT_GLYPH.get(dataset.logistics[unit.unit_id].kind, "?")
        for cell in unit_footprint(dataset, unit):
            put(cell, glyph)
    for entry in layout.entries:
        put(entry.cell, "@")
    header = "   " + "".join(str(x % 10) for x in range(layout.width))
    rows = [f"{y:2d} " + "".join(row) for y, row in enumerate(grid)]
    return "\n".join([header, *rows])
