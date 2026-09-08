"""Repacking: withdraw a spatial neighbourhood of free cells, every other time one at the extent's edge, and reconnect it at ranked anchors, in one attempt."""

import random
from typing import Any

from kohakulayout.ir import Refusal
from kohakulayout.ir.geometry import rotate_size
from kohakulayout.solvers.regional.candidates import Proposals, is_free


class RepackMoves:
    def __init__(
        self, world: Any, settings: dict[str, Any], rng: random.Random
    ) -> None:
        self.world = world
        self.settings = settings
        self.rng = rng

    def edge_cells(self, free: list[str]) -> list[str]:
        """The free cells whose footprint reaches the placed extent's last row or last column."""
        placed = self.world.placements
        far: dict[str, tuple[int, int]] = {}
        for cell_id in free:
            p = placed[cell_id]
            fp = self.world.footprint_of(cell_id)
            w, h = rotate_size(fp.width, fp.height, p.rot)
            far[cell_id] = (p.x + w - 1, p.y + h - 1)
        max_x = max(x for x, _ in far.values())
        max_y = max(y for _, y in far.values())
        return [c for c, (x, y) in far.items() if x == max_x or y == max_y]

    def choose(self) -> list[str]:
        """A neighbourhood around a random free cell, or every other time around one on the extent's edge."""
        world = self.world
        placed = world.placements
        free = sorted(c for c in placed if is_free(world.netlist.cells[c]))
        if len(free) < 2:
            return []
        roots = self.edge_cells(free) if self.rng.random() < 0.5 else free
        root = self.rng.choice(roots)
        rx, ry = placed[root].x, placed[root].y
        ordered = sorted(
            free, key=lambda c: (abs(placed[c].x - rx) + abs(placed[c].y - ry), c)
        )
        size = self.rng.randint(2, max(2, self.settings["repack_size"]))
        selected = ordered[:size]
        self.rng.shuffle(selected)
        return selected

    def execute(self, builder: Any, selected: list[str]) -> Refusal | None:
        """The action: every selected cell withdrawn, then re-inserted through ranked proposals."""
        for cell_id in selected:
            builder.withdraw(cell_id)
        proposals = Proposals(
            self.world, {"candidates": self.settings["repack_candidates"]}
        )
        proposals.reset(self.settings["repack_gap"])
        for cell_id in selected:
            for anchor in proposals.ranked(cell_id, 1, self.rng):
                if not builder.admits(cell_id, anchor.x, anchor.y, anchor.rot):
                    continue
                if builder.place(cell_id, anchor) is None:
                    proposals.occupy(cell_id, anchor.x, anchor.y, anchor.rot)
                    break
            else:
                return Refusal(
                    stage="unrouted",
                    subject=f"cell:{cell_id}",
                    detail="repack could not reconnect it",
                )
        return None


__all__ = ["RepackMoves"]
