"""Assessment: the framework metrics from a world, the pack's terms, every finding, and the verdict."""

from typing import Any

from kohakulayout.ir import FRAMEWORK_METRICS, Assessment, Layout
from kohakulayout.ir.geometry import footprint_cells
from kohakulayout.verify import run


def metrics(world: Any) -> dict[str, Any]:
    """The framework metrics: placed, missing, routed, unrouted, extent, area, wire cells, units, overflow."""
    netlist = world.netlist
    _, _, width, height = world.extent()
    wire_cells = 0
    for wire in world.wires.values():
        seen: set[tuple[str, tuple[int, int]]] = set()
        for segment in wire.segments:
            seen.update((segment.layer, xy) for xy in segment.cells)
        wire_cells += len(seen)
    overflow = 0
    for cell_id, placement in world.placements.items():
        fp = world.footprint_of(cell_id)
        cells = footprint_cells(
            placement.x, placement.y, fp.width, fp.height, placement.rot
        )
        overflow += sum(1 for xy in cells if not world.in_build(xy))
    out = {
        "placed": len(world.placements),
        "missing": len(netlist.cells) - len(world.placements),
        "routed": len(world.wires),
        "unrouted": len(netlist.nets) - len(world.wires),
        "extent_w": width,
        "extent_h": height,
        "area": width * height,
        "wire_cells": wire_cells,
        "units": len(world.units),
        "overflow": overflow,
    }
    assert tuple(out) == FRAMEWORK_METRICS
    return out


def assess(world: Any, layout: Layout | None = None) -> Assessment:
    """L1 for the world's current state, or for ``layout`` when given."""
    frozen = layout if layout is not None else world.freeze()
    values = metrics(world)
    values.update(world.physics.objective.terms(frozen, values))
    findings = run(world, frozen, values)
    complete = values["missing"] == 0 and values["unrouted"] == 0
    valid = complete and not any(f.severity == "error" for f in findings)
    return Assessment(
        layout=frozen.digest(),
        metrics=values,
        findings=findings,
        complete=complete,
        valid=valid,
    )


__all__ = ["assess", "metrics"]
