"""Repacking: withdraw a spatial neighbourhood of free cells and reconnect it at ranked anchors, in one attempt."""

import random
from typing import Any

from kohakulayout.ir import Refusal
from kohakulayout.solvers.regional.candidates import Proposals, is_free


class RepackMoves:
    def __init__(
        self, world: Any, settings: dict[str, Any], rng: random.Random
    ) -> None:
        self.world = world
        self.settings = settings
        self.rng = rng

    def choose(self) -> list[str]:
        world = self.world
        placed = world.placements
        free = sorted(c for c in placed if is_free(world.netlist.cells[c]))
        if len(free) < 2:
            return []
        root = self.rng.choice(free)
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
