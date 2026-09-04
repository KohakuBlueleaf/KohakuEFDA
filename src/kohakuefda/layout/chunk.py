"""Blueprint-sized modules: tiles of at most 50×50 cells, halved while they hold too many entities."""

from kohakuefda.layout.geometry import machine_footprint
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.layout import Cell, Layout, Module


def _anchors(dataset: Dataset, layout: Layout) -> dict[str, Cell]:
    anchors: dict[str, Cell] = {}
    for placed in layout.machines:
        cells = machine_footprint(dataset, placed)
        anchors[placed.id] = (min(c[0] for c in cells), min(c[1] for c in cells))
    for unit in layout.units:
        anchors[unit.id] = (unit.x, unit.y)
    for segment in layout.segments:
        if segment.cells:
            anchors[segment.id] = segment.cells[0]
    return anchors


def chunk(dataset: Dataset, layout: Layout) -> list[Module]:
    """Modules in build order (top-left first) covering the layout's bounding box."""
    anchors = _anchors(dataset, layout)
    if not anchors:
        return []
    max_side = min(dataset.constants.blueprint_max_x, dataset.constants.blueprint_max_z)
    max_nodes = dataset.constants.blueprint_max_nodes
    xs = [c[0] for c in anchors.values()]
    ys = [c[1] for c in anchors.values()]
    boxes: list[tuple[int, int, int, int]] = []
    x0, y0 = min(xs), min(ys)
    for ty in range(y0, max(ys) + 1, max_side):
        for tx in range(x0, max(xs) + 1, max_side):
            boxes.append((tx, ty, max_side, max_side))
    modules: list[Module] = []
    while boxes:
        bx, by, bw, bh = boxes.pop(0)
        inside = sorted(
            eid
            for eid, (x, y) in anchors.items()
            if bx <= x < bx + bw and by <= y < by + bh
        )
        if not inside:
            continue
        if len(inside) > max_nodes and (bw > 1 or bh > 1):
            if bw >= bh:
                half = bw // 2
                boxes[:0] = [(bx, by, half, bh), (bx + half, by, bw - half, bh)]
            else:
                half = bh // 2
                boxes[:0] = [(bx, by, bw, half), (bx, by + half, bw, bh - half)]
            continue
        modules.append(
            Module(
                id=f"m{len(modules)}",
                x=bx,
                y=by,
                width=bw,
                height=bh,
                entities=inside,
            )
        )
    return modules
