"""Compaction proposals over a complete layout: close an empty line, press toward a side, pull a cell toward its partners."""

import random
from itertools import pairwise
from typing import Any

from kohakulayout.ir.geometry import footprint_cells
from kohakulayout.physics.protocol import Anchor
from kohakulayout.solvers.regional.candidates import is_free

Anchors = dict[str, tuple[int, int, int]]


def relocate(builder: Any, moves: Anchors) -> Any:
    """Withdraw every listed cell, then place each at its new anchor; the first refusal ends the attempt."""
    for cell_id in moves:
        if cell_id in builder.placements:
            builder.withdraw(cell_id)
    for cell_id, (x, y, rot) in moves.items():
        refusal = builder.place(cell_id, Anchor(x=x, y=y, rot=rot))
        if refusal is not None:
            return refusal
    return None


def standing_cells(world: Any) -> dict[str, tuple]:
    out = {}
    for cell_id, placement in world.placements.items():
        fp = world.footprint_of(cell_id)
        out[cell_id] = footprint_cells(
            placement.x, placement.y, fp.width, fp.height, placement.rot
        )
    return out


def cut_candidates(
    world: Any, movable: frozenset[str]
) -> list[tuple[tuple[int, int], Anchors]]:
    """For every empty line inside the extent, the relocation that closes it, ranked by area then wire estimate."""
    cells_of = standing_cells(world)
    standing = {c for cells in cells_of.values() for c in cells}
    if not standing:
        return []
    xs = [c[0] for c in standing]
    ys = [c[1] for c in standing]
    bbox = (min(xs), min(ys), max(xs) + 1, max(ys) + 1)
    placed = world.placements
    candidates: dict[tuple, tuple[tuple[int, int], Anchors]] = {}
    for axis in (0, 1):
        lines = sorted(
            set(range(bbox[axis], bbox[axis + 2])) - {c[axis] for c in standing}
        )
        for line in lines:
            for direction in (-1, 1):
                moved = {
                    c
                    for c, p in placed.items()
                    if c in movable
                    and (
                        (p.x, p.y)[axis] > line
                        if direction == -1
                        else (p.x, p.y)[axis] < line
                    )
                }
                if not moved:
                    continue
                anchors: Anchors = {}
                for c, p in placed.items():
                    dx = direction if axis == 0 and c in moved else 0
                    dy = direction if axis == 1 and c in moved else 0
                    anchors[c] = (p.x + dx, p.y + dy, p.rot)
                key = tuple(sorted(anchors.items()))
                if key in candidates:
                    continue
                shifted = [
                    (
                        (
                            x + (direction if axis == 0 else 0),
                            y + (direction if axis == 1 else 0),
                        )
                        if c in moved
                        else (x, y)
                    )
                    for c, cells in cells_of.items()
                    for x, y in cells
                ]
                width = max(x for x, _ in shifted) - min(x for x, _ in shifted) + 1
                height = max(y for _, y in shifted) - min(y for _, y in shifted) + 1
                wire = 0
                for net in world.netlist.nets.values():
                    refs = [r.cell for r in net.pins() if r.cell in anchors]
                    for a, b in pairwise(refs):
                        wire += abs(anchors[a][0] - anchors[b][0]) + abs(
                            anchors[a][1] - anchors[b][1]
                        )
                candidates[key] = (
                    (width * height, wire),
                    {
                        c: a
                        for c, a in anchors.items()
                        if a != (placed[c].x, placed[c].y, placed[c].rot)
                    },
                )
    return sorted(candidates.values(), key=lambda item: item[0])


def press_candidates(
    world: Any, movable: frozenset[str], axis: int, step: int
) -> Anchors:
    """Every movable cell slid toward one side as far as free footprints allow, the farthest first."""
    placed = world.placements
    cells_of = standing_cells(world)
    order = sorted(placed, key=lambda c: (placed[c].x, placed[c].y)[axis] * -step)
    taken = {
        c for cell_id in order if cell_id not in movable for c in cells_of[cell_id]
    }
    moves: Anchors = {}
    for cell_id in order:
        p = placed[cell_id]
        spot = [p.x, p.y, p.rot]
        if cell_id not in movable:
            continue
        cells = cells_of[cell_id]
        while True:
            moved = [(x + step, y) if axis == 0 else (x, y + step) for x, y in cells]
            if any(not world.in_build(c) or c in taken for c in moved):
                break
            spot[axis] += step
            cells = moved
        taken.update(cells)
        if spot[axis] != (p.x, p.y)[axis]:
            moves[cell_id] = (spot[0], spot[1], spot[2])
    return moves


SIDES = ((0, -1), (1, -1), (0, 1), (1, 1))


class CompactionMoves:
    """Sample cut and pull proposals; the world decides feasibility when they are attempted."""

    def __init__(
        self, world: Any, settings: dict[str, Any], rng: random.Random
    ) -> None:
        self.world = world
        self.settings = settings
        self.rng = rng
        self.signature: str | None = None
        self.cuts: list[tuple[tuple[int, int], Anchors]] = []
        self.movable = frozenset(
            c
            for c, cell in world.netlist.cells.items()
            if cell.constraint.kind == "free"
        )
        self.neighbours: dict[str, set[str]] = {c: set() for c in world.netlist.cells}
        for net in world.netlist.nets.values():
            cells = [r.cell for r in net.pins()]
            for a in cells:
                self.neighbours[a].update(b for b in cells if b != a)

    def cut(self) -> Anchors | None:
        signature = self.world.digest()
        if signature != self.signature:
            self.signature = signature
            self.cuts = cut_candidates(self.world, self.movable)
        if not self.cuts:
            return None
        index = self.rng.randrange(
            min(len(self.cuts), self.settings["compact_choices"])
        )
        _, anchors = self.cuts.pop(index)
        return anchors or None

    def press(self) -> Anchors | None:
        axis, step = self.rng.choice(SIDES)
        return press_candidates(self.world, self.movable, axis, step) or None

    def pull(self) -> Anchors | None:
        world = self.world
        placed = world.placements
        choices = [
            c
            for c in self.movable
            if c in placed and is_free(world.netlist.cells[c]) and self.neighbours[c]
        ]
        if not choices:
            return None
        cell_id = self.rng.choice(sorted(choices))
        p = placed[cell_id]
        fp = world.footprint_of(cell_id)
        radius = self.settings["pull_radius"]
        partners = [
            (placed[o].x, placed[o].y) for o in self.neighbours[cell_id] if o in placed
        ]
        occupied = {
            c
            for other, cells in standing_cells(world).items()
            if other != cell_id
            for c in cells
        }
        candidates: list[tuple[int, tuple[int, int, int]]] = []
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if not dx and not dy:
                    continue
                x, y = p.x + dx, p.y + dy
                cells = footprint_cells(x, y, fp.width, fp.height, p.rot)
                if any(not world.in_build(c) or c in occupied for c in cells):
                    continue
                distance = sum(abs(x - px) + abs(y - py) for px, py in partners)
                candidates.append((distance, (x, y, p.rot)))
        candidates.sort()
        if not candidates:
            return None
        _, anchor = self.rng.choice(candidates[: self.settings["compact_choices"]])
        return {cell_id: anchor}


__all__ = [
    "SIDES",
    "Anchors",
    "CompactionMoves",
    "cut_candidates",
    "press_candidates",
    "relocate",
    "standing_cells",
]
