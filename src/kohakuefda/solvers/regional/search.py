"""Seeded frontier construction and spatial/graph neighborhood reconstruction."""

import random

from kohakuefda.framework.context import Context
from kohakuefda.framework.control import Rejected
from kohakuefda.solvers.regional.candidates import Proposals


class Search:
    """Retain routed partial builds and rebuild neighborhoods of missing machines."""

    def __init__(self, context: Context, settings: dict) -> None:
        self.context = context
        self.settings = settings
        self.builder = context.builder()
        self.blocks = context.blocks
        self.rng = random.Random(context.seed)
        self.proposals = Proposals(context, settings)
        self.neighbors = {i: [] for i in self.blocks}
        for link in context.links:
            self.neighbors[link.source].append(link.sink)
            self.neighbors[link.sink].append(link.source)
        self.pressure = {i: 0.0 for i in self.blocks}
        self.best_count = 0
        self.best_mark = None
        self.best_missing = []

    def region(self, trial: int) -> set[str]:
        placed = dict(self.context.anchors)
        free = [
            i
            for i in placed
            if self.blocks[i].kind != "depot"
            and self.blocks[i].constraint not in ("slot", "edge")
        ]
        near = sorted(
            {j for i in self.best_missing for j in self.neighbors[i] if j in free}
        )
        near = near or free
        if not near:
            return set()
        pivot = self.rng.choice(near)
        x, y, _ = placed[pivot]
        radius = self.settings["radius"] + trial % self.settings["radius_cycle"]
        removed = {
            i for i in free if abs(placed[i][0] - x) + abs(placed[i][1] - y) < radius
        }
        if trial % self.settings["neighbor_cycle"] == 0:
            removed.update(near)
        if trial % self.settings["expand_cycle"] == 0:
            removed.update(
                j for i in tuple(removed) for j in self.neighbors[i] if j in free
            )
        return removed

    def prepare(self, trial: int) -> None:
        self.builder.reset()
        if (
            self.best_mark is None
            or self.best_count <= len(self.blocks) * self.settings["repair_threshold"]
            or trial % self.settings["restart_cycle"] == 0
        ):
            return
        self.builder.restore(self.best_mark)
        removed = self.region(trial) | set(self.best_missing)
        if self.builder.withdraw(tuple(removed)).status != "removed":
            self.builder.reset()
            return
        for block_id in self.best_missing:
            self.pressure[block_id] = self.settings["repair_pressure"]

    def ready(self, block_id: str, placed: dict) -> bool:
        block = self.blocks[block_id]
        return (
            block.constraint == "slot"
            or not block.group
            or block.kind == "depot"
            or any(
                i in placed and b.kind == "depot" and b.group == block.group
                for i, b in self.blocks.items()
            )
        )

    def priority(self, i, placed, jitter):
        block = self.blocks[i]
        n = sum(j in placed for j in self.neighbors[i])
        return (
            block.kind == "depot",
            n > 0,
            self.pressure[i] + n / (len(self.neighbors[i]) or 1),
            n,
            block.width * block.height,
            jitter[i],
        )

    def insert(self, block_id, anchors):
        for anchor in anchors:
            if self.builder.place(block_id, anchor).status == "placed":
                self.proposals.occupy(block_id, anchor)
                return True
        return False

    def construct(self, trial: int) -> list[str]:
        remaining = set(self.blocks) - dict(self.context.anchors).keys()
        jitter = {i: self.rng.random() for i in self.blocks}
        self.proposals.reset(self.settings["gap"] + trial % self.settings["gap_cycle"])
        failed = []
        retries = 0
        while remaining:
            self.context.budget.check()
            placed = dict(self.context.anchors)
            ready = [i for i in sorted(remaining) if self.ready(i, placed)]
            if not ready:
                failed.extend(sorted(remaining))
                break

            block_id = max(ready, key=lambda i: self.priority(i, placed, jitter))
            remaining.remove(block_id)
            anchors = self.proposals.ranked(block_id, trial, self.rng)
            if not self.insert(block_id, anchors):
                failed.append(block_id)
            if not remaining and failed and retries < self.settings["refill_rounds"]:
                remaining = set(failed)
                failed = []
                retries += 1
                self.proposals.reset(max(0, self.proposals.gap - 1))
        return failed

    def retain(self, failed: list[str]) -> None:
        for block_id in self.blocks:
            self.pressure[block_id] *= self.settings["pressure_decay"]
        for block_id in failed:
            self.pressure[block_id] += self.settings["failure_pressure"]
        count = len(self.context.anchors)
        if count > self.best_count or (
            count == self.best_count
            and self.rng.random() < self.settings["replace_equal"]
        ):
            if self.best_mark is not None:
                self.builder.release(self.best_mark)
            self.best_count = count
            self.context.diagnostic = self.builder.diagnostic()
            self.best_mark = self.builder.mark()
            placed = dict(self.context.anchors)
            self.best_missing = [i for i in self.blocks if i not in placed]

    def run(self) -> str:
        try:
            for trial in range(self.settings["attempts"]):
                self.context.budget.charge("regional_attempts")
                self.prepare(trial)
                failed = self.construct(trial)
                self.retain(failed)
                self.context.emit(
                    "progress",
                    {
                        "phase": "regional",
                        "attempt": trial + 1,
                        "placed": len(self.context.anchors),
                        "best_placed": self.best_count,
                        "total": len(self.blocks),
                    },
                )
                if len(self.context.anchors) == len(self.blocks):
                    try:
                        self.builder.finish()
                    except Rejected:
                        continue
                    self.context.frame("build")
                    return "completed"
            return "no_solution_found"
        finally:
            if self.best_mark is not None:
                self.builder.release(self.best_mark)
