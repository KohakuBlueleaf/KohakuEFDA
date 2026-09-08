"""The frozen forms of a world: a Layout out of it, and a Layout adopted into it."""

from typing import Any

from kohakulayout.ir import Layout, Placement
from kohakulayout.ir.geometry import footprint_cells


def freeze(world: Any, hierarchical: bool = False) -> Layout:
    """The world as L2; with ``hierarchical`` every fully placed instance folds back to its anchor."""
    placements = dict(world.placements)
    instances: dict[str, Placement] = {}
    if hierarchical:
        for instance_id, anchor in world.instance_anchors.items():
            leaves = [
                leaf for leaf, owner in world.membership.items() if owner == instance_id
            ]
            if leaves and all(leaf in placements for leaf in leaves):
                instances[instance_id] = anchor
                for leaf in leaves:
                    del placements[leaf]
    return Layout(
        problem=world.problem.digest(),
        placements=placements,
        instances=instances,
        wires=dict(world.wires),
        units=dict(world.units),
        reservations=tuple(world.reservations.values()),
    )


def load(world: Any, layout: Layout) -> None:
    """Occupy the kernel from a flat layout and replace the world's records; no checks."""
    flat = layout.flatten(world.problem.netlist)
    world.kernel.clear()
    world.placements, world.wires, world.units, world.reservations = {}, {}, {}, {}
    for key, placement in flat.placements.items():
        fp = world.footprint_of(key)
        if fp is None:
            continue
        cells = footprint_cells(
            placement.x, placement.y, fp.width, fp.height, placement.rot
        )
        for layer in world.layers_for(fp):
            world.kernel.occupy(layer, cells, f"cell:{key}")
        world.placements[key] = placement
    for key, wire in flat.wires.items():
        for segment in wire.segments:
            world.kernel.occupy(segment.layer, segment.cells, f"wire:{key}")
        world.wires[key] = wire
    for key, unit in flat.units.items():
        fp = world.library.get(unit.footprint)
        cells = (
            footprint_cells(unit.x, unit.y, fp.width, fp.height, unit.rot)
            if fp
            else ((unit.x, unit.y),)
        )
        for layer in world.layers_for(fp) if fp else (world.fabric.layers[0],):
            world.kernel.occupy(layer, cells, f"unit:{key}")
        world.units[key] = unit
    for reservation in flat.reservations:
        world.kernel.occupy(
            reservation.layer, reservation.cells, f"reserve:{reservation.tag}"
        )
        world.reservations[reservation.tag] = reservation
    world.seq = 0


__all__ = ["freeze", "load"]
