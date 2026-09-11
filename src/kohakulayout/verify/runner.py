"""The verify runner: structural findings, occupancy, legality, uncovered needs, the flow evaluation when the pack asks, then every rule."""

from typing import Any

from kohakulayout.flow import evaluate
from kohakulayout.ir import Finding, Layout, Placement
from kohakulayout.ir.geometry import footprint_cells
from kohakulayout.physics import Occupant, run_rules
from kohakulayout.physics.fields import reach_cells, satisfied
from kohakulayout.verify.structural import structural


def run(world: Any, layout: Layout, metrics: dict[str, Any]) -> tuple[Finding, ...]:
    """Every finding for ``layout`` in the world's problem: structural first, then the pack's rules."""
    found = structural(layout, world.problem.netlist, world.fabric)
    found += occupancy(world, layout)
    found += legal(world, layout)
    found += uncovered(world, layout)
    flow = world.physics.flow
    if getattr(flow, "evaluates", False):
        found += evaluate(
            world.problem.netlist,
            flow,
            world.fabric,
            evaluator=getattr(flow, "evaluator", "fixedpoint"),
            layout=layout,
        ).findings
    return found + run_rules(world.physics.rules, world, layout, metrics)


FIELD = "kl.field"
OCCUPANCY = "kl.occupancy"
LEGAL = "kl.legal"


def occupancy(world: Any, layout: Layout) -> tuple[Finding, ...]:
    """Two occupants on one cell of one layer, unless the pack's carriers let them share it."""
    held: dict[tuple[str, tuple[int, int]], list[tuple[str, Occupant]]] = {}
    netlist = world.netlist
    for cell_id, placement in layout.placements.items():
        fp = netlist.footprint_for(cell_id)
        if fp is None:
            continue
        cells = footprint_cells(
            placement.x, placement.y, fp.width, fp.height, placement.rot
        )
        occupant = Occupant(kind="cell", id=cell_id)
        for layer in world.layers_for(fp):
            for xy in cells:
                held.setdefault((layer, xy), []).append((f"cell:{cell_id}", occupant))
    for net_id, wire in layout.wires.items():
        net = netlist.nets.get(net_id)
        occupant = Occupant(
            kind="wire", carrier=net.carrier if net else None, id=net_id
        )
        for segment in wire.segments:
            for xy in segment.cells:
                held.setdefault((segment.layer, xy), []).append(
                    (f"wire:{net_id}", occupant)
                )
    for unit_id, unit in layout.units.items():
        fp = world.library.get(unit.footprint)
        occupant = Occupant(kind="unit", unit_kind=unit.kind, id=unit_id)
        cells = (
            footprint_cells(unit.x, unit.y, fp.width, fp.height, unit.rot)
            if fp
            else ((unit.x, unit.y),)
        )
        for layer in world.layers_for(fp) if fp else (world.fabric.layers[0],):
            for xy in cells:
                held.setdefault((layer, xy), []).append((f"unit:{unit_id}", occupant))
    out: list[Finding] = []
    for (layer, xy), holders in held.items():
        if len(holders) < 2:
            continue
        crossed = any(mine.kind == "unit" for _, mine in holders)
        for index, (first, mine) in enumerate(holders):
            for second, theirs in holders[index + 1 :]:
                if first == second or world.share.may_share(mine, theirs):
                    continue
                if crossed and mine.kind == "wire" and theirs.kind == "wire":
                    continue
                out.append(
                    Finding(
                        rule=OCCUPANCY,
                        severity="error",
                        subject=first,
                        message=f"{first} and {second} both hold {xy} on {layer}",
                    )
                )
    return tuple(out)


def legal(world: Any, layout: Layout) -> tuple[Finding, ...]:
    """Every placement the pack's boundaries refuse, asked again of the whole layout."""
    out: list[Finding] = []
    for cell_id, placement in layout.placements.items():
        if cell_id not in world.netlist.cells:
            continue
        refusal = world.physics.boundaries.legal(
            world,
            Placement(cell=cell_id, x=placement.x, y=placement.y, rot=placement.rot),
        )
        if refusal is not None:
            out.append(
                Finding(
                    rule=LEGAL,
                    severity="error",
                    subject=f"cell:{cell_id}",
                    message=f"{cell_id}: {refusal.detail}",
                )
            )
    return tuple(out)


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


__all__ = ["FIELD", "LEGAL", "OCCUPANCY", "legal", "occupancy", "run", "uncovered"]
