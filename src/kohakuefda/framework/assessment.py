"""Common materialization, measurement and evidence independent of solver policy."""

from collections.abc import Mapping
from types import MappingProxyType

from kohakuefda.flow.evaluate import evaluate
from kohakuefda.framework.control import Rejected
from kohakuefda.layout.assemble import assemble
from kohakuefda.layout.chunk import chunk
from kohakuefda.layout.geometry import machine_footprint, unit_footprint
from kohakuefda.layout.place import placement_of
from kohakuefda.layout.site import Site
from kohakuefda.model.geometry import rotate_edge
from kohakuefda.model.layout import Entry, Layout
from kohakuefda.model.plan import Finding, Plan
from kohakuefda.model.solver import Assessment, Issue, Screen
from kohakuefda.verify.rules.geometry import check_layout
from kohakuefda.verify.rules.rates import rate_findings


class AreaWire:
    """Area first, summed routing path cells second; no feasibility penalties."""

    name = "area-wire-v1"

    def key(self, assessment: Assessment) -> tuple[float, float]:
        return self.key_metrics(dict(assessment.metrics))

    def key_metrics(self, metrics: Mapping[str, float]) -> tuple[float, float]:
        return metrics["area"], metrics["wire_path_cells"]


def materialize(site: Site) -> tuple[Layout, list[tuple[int, int]], list[str]]:
    """Build actual entities from the live routing realization and selected support."""
    pylons, uncovered = site.pylons()
    blocks = [
        b
        for b in site.blocks.values()
        if b.id in site.placed and b.constraint != "edge"
    ]
    layout = assemble(
        site.dataset,
        blocks,
        site.dataset.version.id,
        site.netlist.scenario.basement,
        site.width,
        site.height,
        site.area,
        pylons,
        site.pylon.machine_id,
    )
    for block in site.blocks.values():
        if block.id not in site.placed or block.constraint != "edge":
            continue
        key = next(iter(block.pins))
        pin = block.pins[key]
        cell, edge = block.pin_world(key)
        layout.entries.append(
            Entry(
                id=block.id,
                item_id=pin.item_id,
                rate=pin.rate,
                x=cell[0],
                y=cell[1],
                edge=rotate_edge(edge, 180),
            )
        )
    site.router.emit(layout)
    layout.modules = chunk(site.dataset, layout)
    return layout, pylons, uncovered


def metrics_of(site: Site, layout: Layout, pylons: list) -> dict[str, float]:
    occupied = set()
    for placed in layout.machines:
        occupied.update(machine_footprint(site.dataset, placed))
    for unit in layout.units:
        occupied.update(unit_footprint(site.dataset, unit))
    for segment in layout.segments:
        occupied.update(segment.cells)
    occupied.update(e.cell for e in layout.entries)
    x0, y0, x1, y1 = site.area
    occupied = {(x, y) for x, y in occupied if x0 <= x < x1 and y0 <= y < y1}
    width = (
        max(x for x, _ in occupied) - min(x for x, _ in occupied) + 1 if occupied else 0
    )
    height = (
        max(y for _, y in occupied) - min(y for _, y in occupied) + 1 if occupied else 0
    )
    return {
        "area": float(width * height),
        "width": float(width),
        "height": float(height),
        "waste": float(width * height - len(occupied)),
        "occupied_cells": float(len(occupied)),
        "length": float(sum(len(s.cells) for s in layout.segments)),
        "wire_path_cells": float(site.wire_cells()),
        "pylons": float(len(pylons)),
        "junctions": float(site.junctions()),
        "bricks_underused": float(
            sum(
                1
                for b in site.blocks.values()
                if b.kind in ("depot", "unloader", "loader")
                for p in b.pins.values()
                if p.rate < site.dataset.constants.belt_per_min
            )
        ),
    }


def assess(
    site: Site,
    plan: Plan | None = None,
    rates: bool = False,
    screen: Screen | None = None,
) -> tuple:
    """Materialize and check; rates remain not_checked without an explicit plan check."""
    layout, pylons, uncovered = materialize(site)
    metrics = metrics_of(site, layout, pylons)
    if screen is not None and not screen(MappingProxyType(metrics)):
        raise Rejected(
            "solver screened out measured candidate before validation", "screened"
        )
    findings = list(site.board.findings) + list(site.netlist.findings)
    for block_id in site.unplaced():
        findings.append(
            Finding(
                rule="layout.unplaced",
                severity="error",
                subject=block_id,
                message="construction did not place this required cell",
            )
        )
    for wire in site.unrouted():
        findings.append(
            Finding(
                rule="layout.unrouted",
                severity="error",
                subject=wire.id,
                message="no route found for this ready connection",
            )
        )
    for block_id in uncovered:
        findings.append(
            Finding(
                rule="layout.uncovered",
                severity="error",
                subject=block_id,
                message="no pylon can cover this machine",
            )
        )
    if site.faults():
        findings.append(
            Finding(
                rule="layout.group_faults",
                severity="error",
                subject="layout",
                message="mandatory spatial group constraints failed",
            )
        )
    findings += check_layout(site.dataset, layout)
    geometry = "fail" if any(f.severity == "error" for f in findings) else "pass"
    rate_status = "not_checked"
    if rates and plan is not None:
        evaluated = evaluate(site.dataset, layout)
        rate_errors = rate_findings(site.dataset, plan, evaluated)
        rate_status = (
            "fail" if any(f.severity == "error" for f in rate_errors) else "pass"
        )
        findings += rate_errors
    assessment = Assessment(
        not site.unplaced(),
        geometry,
        "pass" if not site.unrouted() and not site.unplaced() else "fail",
        rate_status,
        tuple(Issue(f.rule, f.severity, f.subject, f.message) for f in findings),
        tuple(metrics.items()),
    )
    placement = placement_of(
        list(site.blocks.values()),
        pylons,
        layout.entries,
        site.dataset.version.id,
        site.board.square,
        site.board.grid,
        site.area,
        0,
        metrics["area"],
        metrics,
        findings,
    )
    return layout, placement, assessment
