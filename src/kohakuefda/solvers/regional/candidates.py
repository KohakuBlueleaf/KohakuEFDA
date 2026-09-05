"""Port-distance proposals and construction-only machine clearances."""

import random

import numpy as np

from kohakuefda.framework.context import Context
from kohakuefda.model.geometry import (
    ROTATIONS,
    Edge,
    edge_step,
    rotate_cell,
    rotate_edge,
)
from kohakuefda.model.solver import Anchor


class Proposals:
    """Generate positions against current footprints and opposite routing endpoints."""

    def __init__(self, context: Context, settings: dict) -> None:
        self.context = context
        self.settings = settings
        self.area = context.area
        x0, y0, x1, y1 = self.area
        self.occupied = np.zeros((y1 - y0, x1 - x0), dtype=np.int8)
        self.ports = {}
        for block_id, block in context.blocks.items():
            for rotation in ROTATIONS:
                for lane in block.lanes:
                    offsets = []
                    for choice in lane.choices:
                        x, y = rotate_cell(
                            *choice.cell, block.width, block.height, rotation
                        )
                        dx, dy = edge_step(rotate_edge(Edge(choice.edge), rotation))
                        offsets.append((x + dx, y + dy))
                    self.ports[block_id, lane.id, rotation] = tuple(offsets)
        self.gap = 0

    def reset(self, gap: int) -> None:
        self.gap = gap
        self.occupied[:] = 0
        for block_id, anchor in self.context.anchors:
            self.occupy(block_id, anchor)

    def occupy(self, block_id: str, anchor: Anchor) -> None:
        x0, y0, x1, y1 = self.area
        x, y, rotation = anchor
        block = self.context.blocks[block_id]
        for dx, dy in block.footprints[rotation // 90]:
            px, py = x + dx - x0, y + dy - y0
            if 0 <= px < x1 - x0 and 0 <= py < y1 - y0:
                self.occupied[
                    max(0, py - self.gap) : py + self.gap + 1,
                    max(0, px - self.gap) : px + self.gap + 1,
                ] = 1

    def anchors(self, block_id: str) -> list[Anchor]:
        ctx = self.context
        block = ctx.blocks[block_id]
        if block.constraint == "slot":
            return list(ctx.slot_anchors(block_id))
        if block.constraint == "edge":
            return list(ctx.border_anchors())
        if block.group and any(
            ctx.blocks[i].group == block.group for i, _ in ctx.anchors
        ):
            return list(ctx.group_anchors(block_id))
        x0, y0, _, _ = self.area
        if block.kind == "depot":
            step = self.settings["depot_step"]
            return [
                (x0 + dx, y0 + dy, rotation)
                for dy in range(step, self.settings["depot_window"], step)
                for dx in range(step, self.settings["depot_window"], step)
                for rotation in ROTATIONS
            ]
        integral = np.pad(self.occupied, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
        anchors = []
        for rotation in ROTATIONS:
            width, height = (
                (block.width, block.height)
                if rotation % 180 == 0
                else (block.height, block.width)
            )
            if height > self.occupied.shape[0] or width > self.occupied.shape[1]:
                continue
            blocked = (
                integral[height:, width:]
                - integral[:-height, width:]
                - integral[height:, :-width]
                + integral[:-height, :-width]
            )
            yy, xx = np.nonzero(blocked == 0)
            anchors.extend((int(x) + x0, int(y) + y0, rotation) for x, y in zip(xx, yy))
        return anchors

    def ranked(self, block_id: str, trial: int, rng: random.Random) -> list[Anchor]:
        ctx = self.context
        anchors = self.anchors(block_id)
        if not anchors:
            return []
        targets = ctx.connection_targets(block_id)
        array = np.array(anchors)
        score = np.zeros(len(anchors))
        for rotation in ROTATIONS:
            mask = array[:, 2] == rotation
            subset = array[mask]
            if not len(subset):
                continue
            values = np.zeros(len(subset))
            for target in targets:
                distances = [
                    np.abs(subset[:, 0] + dx - x) + np.abs(subset[:, 1] + dy - y)
                    for x, y in target.cells
                    for dx, dy in self.ports[block_id, target.lane_id, rotation]
                ]
                values += (
                    np.minimum.reduce(distances)
                    if distances
                    else self.settings["closed_cost"]
                )
            score[mask] = values
        x0, y0, x1, y1 = self.area
        if not ctx.anchors or (not targets and ctx.blocks[block_id].kind != "depot"):
            score += self.settings["center_weight"] * (
                np.abs(array[:, 0] - (x0 + (x1 - x0) // 3))
                + np.abs(array[:, 1] - (y0 + (y1 - y0) // 3))
            )
        else:
            score += self.settings["corner_weight"] * (
                array[:, 0] - x0 + array[:, 1] - y0
            )
        if trial:
            noise = np.random.default_rng(rng.randrange(2**32))
            score += noise.uniform(0, self.settings["jitter"] + trial % 4, len(score))
        indices = np.argsort(score, kind="stable")[: self.settings["candidates"]]
        return [anchors[index] for index in indices]
