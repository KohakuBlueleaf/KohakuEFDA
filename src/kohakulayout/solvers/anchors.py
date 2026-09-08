"""The anchor generator registry: how a solver orders the anchors it tries for a cell."""

import random
from collections.abc import Callable, Iterable
from typing import Any

from kohakulayout.physics.protocol import Anchor
from kohakulayout.solvers.regional.candidates import Proposals

Generator = Callable[[Any, str, random.Random], Iterable[Anchor]]


def every(world: Any, cell_id: str, rng: random.Random) -> Iterable[Anchor]:
    """The pack's own stream: every legal anchor for the cell's constraint."""
    return world.anchors(cell_id)


def facing(world: Any, cell_id: str, rng: random.Random) -> Iterable[Anchor]:
    """Clear windows ranked by how close the cell's pins land to the pins they must reach."""
    proposals = Proposals(world)
    proposals.reset(0)
    return proposals.ranked(cell_id, 0, rng)


def frontier(world: Any, cell_id: str, rng: random.Random) -> Iterable[Anchor]:
    """Anchors touching the placed extent first, then the rest of the pack's stream."""
    x0, y0, w, h = world.extent()
    fp = world.footprint_of(cell_id)
    if w == 0 or fp is None:
        return world.anchors(cell_id)
    near: list[Anchor] = []
    far: list[Anchor] = []
    reach = max(fp.width, fp.height) + 1
    for anchor in world.anchors(cell_id):
        touching = x0 - reach <= anchor.x <= x0 + w and y0 - reach <= anchor.y <= y0 + h
        (near if touching else far).append(anchor)
    return [*near, *far]


def group(world: Any, cell_id: str, rng: random.Random) -> Iterable[Anchor]:
    """Windows around placed members of the cell's group, or the facing stream when none is placed."""
    cell = world.netlist.cells[cell_id]
    proposals = Proposals(world)
    proposals.reset(0)
    if cell.group is not None:
        members = [
            m
            for m in world.netlist.groups[cell.group].members
            if m in world.placements and m != cell_id
        ]
        if members:
            return proposals.group_window(cell_id, members)
    return proposals.ranked(cell_id, 0, rng)


ANCHORS: dict[str, Generator] = {
    "every": every,
    "facing": facing,
    "frontier": frontier,
    "group": group,
}


def anchors_for(
    name: str, world: Any, cell_id: str, rng: random.Random
) -> Iterable[Anchor]:
    return ANCHORS[name](world, cell_id, rng)


__all__ = [
    "ANCHORS",
    "Generator",
    "anchors_for",
    "every",
    "facing",
    "frontier",
    "group",
]
