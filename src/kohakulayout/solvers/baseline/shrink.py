"""Greedy compaction over a complete layout: carve an empty line, press toward a side, nudge toward partners."""

from typing import Any

from kohakulayout.ir.geometry import footprint_cells
from kohakulayout.solvers.local.compact import (
    SIDES,
    Anchors,
    press_candidates,
    relocate,
    standing_cells,
)
from kohakulayout.solvers.regional.search import neighbours_of


class Shrink:
    def __init__(self, ctx: Any, rounds: int) -> None:
        self.ctx = ctx
        self.world = ctx.world
        self.rounds = rounds
        self.neighbours = neighbours_of(self.world.netlist)
        self.movable = frozenset(
            c
            for c, cell in self.world.netlist.cells.items()
            if cell.constraint.kind == "free"
        )
        self.seen: set[tuple[str, tuple]] = set()

    def take(self, moves: Anchors) -> bool:
        """Attempt the relocation; keep it when the assessment ranks better, or ranks equal with fewer wire cells."""
        ctx = self.ctx
        key = (self.world.digest(), tuple(sorted(moves.items())))
        if key in self.seen:
            return False
        self.seen.add(key)
        token = ctx.snapshot()
        before = (
            ctx.best_assessment if ctx.best_assessment is not None else ctx.assess()
        )
        result = ctx.attempt(lambda b: relocate(b, moves), label="rebuild")
        if result.refusal is not None:
            ctx.restore(token)
            return False
        after = ctx.consider()
        if after is None:
            ctx.restore(token)
            return False
        objective = ctx.physics.objective
        better = ctx.rank(after, objective) < ctx.rank(before, objective)
        plateau = (
            ctx.rank(after, objective) == ctx.rank(before, objective)
            and after.metrics["wire_cells"] < before.metrics["wire_cells"]
        )
        if not better and not plateau:
            ctx.restore(token)
            return False
        return True

    def carve(self) -> bool:
        placed = self.world.placements
        standing = {c for cells in standing_cells(self.world).values() for c in cells}
        if not standing:
            return False
        for axis in (0, 1):
            low = min(c[axis] for c in standing)
            high = max(c[axis] for c in standing)
            lines = set(range(low, high + 1)) - {c[axis] for c in standing}
            for line in sorted(lines, reverse=True):
                moves: Anchors = {}
                for cell_id, p in placed.items():
                    spot = [p.x, p.y, p.rot]
                    if cell_id in self.movable and spot[axis] > line:
                        spot[axis] -= 1
                        moves[cell_id] = (spot[0], spot[1], spot[2])
                if moves and self.take(moves):
                    return True
        return False

    def press(self, axis: int, step: int) -> bool:
        moves = press_candidates(self.world, self.movable, axis, step)
        return bool(moves) and self.take(moves)

    def nudge(self) -> bool:
        world = self.world
        placed = world.placements
        for cell_id in sorted(placed):
            if cell_id not in self.movable:
                continue
            p = placed[cell_id]
            partners = [
                (placed[o].x, placed[o].y)
                for o in self.neighbours[cell_id]
                if o in placed
            ]
            steps = sorted(
                ((1, 0), (-1, 0), (0, 1), (0, -1)),
                key=lambda s: sum(
                    abs(p.x + s[0] - px) + abs(p.y + s[1] - py) for px, py in partners
                ),
            )
            fp = world.footprint_of(cell_id)
            for dx, dy in steps:
                if all(
                    world.in_build(c)
                    for c in footprint_cells(
                        p.x + dx, p.y + dy, fp.width, fp.height, p.rot
                    )
                ) and self.take({cell_id: (p.x + dx, p.y + dy, p.rot)}):
                    return True
        return False

    def run(self) -> None:
        for _ in range(self.rounds):
            self.seen.clear()
            if (
                not self.carve()
                and not any(self.press(a, s) for a, s in SIDES)
                and not self.nudge()
            ):
                break
            self.ctx.frame("shrink")


__all__ = ["SIDES", "Shrink"]
