"""The verify runner: structural findings, uncovered needs, the flow evaluation when the pack asks, then every rule."""

from typing import Any

from kohakulayout.flow import evaluate
from kohakulayout.ir import Finding, Layout
from kohakulayout.ir.geometry import footprint_cells
from kohakulayout.physics import run_rules
from kohakulayout.physics.fields import reach_cells, satisfied
from kohakulayout.verify.structural import structural


def run(world: Any, layout: Layout, metrics: dict[str, Any]) -> tuple[Finding, ...]:
    """Every finding for ``layout`` in the world's problem: structural first, then the pack's rules."""
    found = structural(layout, world.problem.netlist, world.fabric)
    found += uncovered(world, layout)
    if getattr(world.physics.flow, "evaluates", False):
        found += evaluate(
            world.problem.netlist, world.physics.flow, world.fabric
        ).findings
    return found + run_rules(world.physics.rules, world, layout, metrics)


FIELD = "kl.field"


def uncovered(world: Any, layout: Layout) -> tuple[Finding, ...]:
    """A placed cell whose need no emitter unit in the layout reaches."""
    fields = world.physics.fields
    emitters = {e.kind: e for e in fields.emitters()}
    by_footprint = {e.footprint.id: e for e in emitters.values()}
    covered: dict[str, set] = {kind: set() for kind in emitters}
    for unit in layout.units.values():
        emitter = by_footprint.get(unit.footprint)
        if emitter is not None and unit.owner == f"field:{emitter.kind}":
            covered[emitter.kind] |= reach_cells(emitter, unit.x, unit.y)
    out: list[Finding] = []
    netlist = world.netlist
    for cell_id, placement in layout.placements.items():
        cell = netlist.cells.get(cell_id)
        fp = netlist.footprint_for(cell_id)
        if cell is None or fp is None:
            continue
        cells = footprint_cells(
            placement.x, placement.y, fp.width, fp.height, placement.rot
        )
        for kind in fields.needs(cell):
            emitter = emitters.get(kind)
            if emitter is None or not satisfied(
                cells, frozenset(covered[kind]), emitter.reach.partial
            ):
                out.append(
                    Finding(
                        rule=FIELD,
                        severity="error",
                        subject=f"cell:{cell_id}",
                        message=f"{cell_id} needs {kind!r} and nothing covers it",
                    )
                )
    return tuple(out)


__all__ = ["FIELD", "run", "uncovered"]
