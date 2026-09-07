"""Realize structural packing preferences through coupled public placement operations."""

import random

import numpy as np

from kohakuefda.framework.control import Rejected
from kohakuefda.model.geometry import ROTATIONS
from kohakuefda.solvers.local.frontier import endpoint_distances
from kohakuefda.solvers.regional import DEFAULTS as REGIONAL_DEFAULTS
from kohakuefda.solvers.regional.candidates import Proposals


class TreeProposals(Proposals):
    """Combine tree geometry with compatible opposite-endpoint distances."""

    def __init__(self, context, settings):
        super().__init__(
            context, {**REGIONAL_DEFAULTS, "candidates": settings["tree_candidates"]}
        )
        self.bias = settings["tree_pull"]
        self.hints = {}

    def ranked(self, block_id, trial, rng):
        if block_id not in self.hints:
            return super().ranked(block_id, trial, rng)
        anchors = self.anchors(block_id)
        if not anchors:
            return []
        array = np.array(anchors)
        score = np.zeros(len(anchors))
        targets = self.context.connection_targets(block_id)
        maps = {
            target.cells: endpoint_distances(self.context.view.grid, target.cells)
            for target in targets
            if target.cells
        }
        for rotation in ROTATIONS:
            mask = array[:, 2] == rotation
            subset = array[mask]
            if not len(subset):
                continue
            values = np.zeros(len(subset))
            for target in targets:
                distances = (
                    [
                        maps[target.cells][subset[:, 1] + dy, subset[:, 0] + dx]
                        for dx, dy in self.ports[block_id, target.lane_id, rotation]
                    ]
                    if target.cells
                    else []
                )
                values += (
                    np.minimum.reduce(distances)
                    if distances
                    else self.settings["closed_cost"]
                )
            score[mask] = values
        x, y, r = self.hints[block_id]
        score += self.bias * (
            abs(array[:, 0] - x) + abs(array[:, 1] - y) + (array[:, 2] != r)
        )
        indices = np.argsort(score, kind="stable")[: self.settings["candidates"]]
        return [anchors[index] for index in indices]


class TreeDecoder:
    """Realize a tree with deterministic routing-aware displacement and retry."""

    def __init__(self, context, settings) -> None:
        self.context = context
        self.settings = settings
        self.proposals = TreeProposals(context, settings)
        self.neighbors = {i: set() for i in context.blocks}
        for link in context.links:
            self.neighbors[link.source].add(link.sink)
            self.neighbors[link.sink].add(link.source)

    def order(self) -> tuple[str, ...]:
        free = {
            i
            for i, b in self.context.blocks.items()
            if b.constraint == "free" and not b.group
        }
        order = []
        while free:
            root = max(
                sorted(free),
                key=lambda i: (
                    sum(j in order for j in self.neighbors[i]),
                    len(self.neighbors[i]),
                ),
            )
            order.append(root)
            free.remove(root)
        return tuple(order)

    def run(self, tree, place, hints=None) -> dict:
        ctx = self.context
        rng = random.Random(ctx.seed)
        hints = hints or tree.pack(ctx.blocks, ctx.area)
        self.proposals.hints = hints
        self.proposals.reset(self.settings["tree_clearance"])
        traversal = {
            tree.labels[node]: rank for rank, node in enumerate(tree.traversal())
        }
        remaining = set(ctx.blocks) - dict(ctx.anchors).keys()
        failed = []
        retries = 0
        while remaining:
            ctx.budget.check()
            placed = dict(ctx.anchors)
            ready = [
                i
                for i in sorted(remaining)
                if ctx.blocks[i].constraint == "slot"
                or not ctx.blocks[i].group
                or ctx.blocks[i].kind == "depot"
                or any(
                    ctx.blocks[j].kind == "depot"
                    and ctx.blocks[j].group == ctx.blocks[i].group
                    for j in placed
                )
            ]
            if not ready:
                break

            def priority(i, placed=placed):
                block = ctx.blocks[i]
                n = sum(j in placed for j in self.neighbors[i])
                return (
                    block.kind == "depot",
                    n > 0,
                    n / max(1, len(self.neighbors[i])),
                    n,
                    -traversal.get(i, -1),
                )

            block_id = max(ready, key=priority)
            remaining.remove(block_id)
            for anchor in self.proposals.ranked(block_id, 0, rng):
                if place(block_id, anchor):
                    self.proposals.occupy(block_id, anchor)
                    break
            else:
                failed.append(block_id)
            if not remaining and failed and retries < 1:
                remaining, failed = set(failed), []
                retries += 1
                self.proposals.reset(0)
        return hints


def workspace_place(workspace, block_id, anchor) -> bool:
    """Try an insertion without hiding scope failures or interrupt exceptions."""
    try:
        workspace.put(block_id, anchor)
        return True
    except Rejected as error:
        if error.status == "scope_required":
            raise
        return False
