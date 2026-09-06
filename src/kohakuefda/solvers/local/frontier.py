"""Optimistic construction potential for the space and connections still needed."""

import numpy as np

from kohakuefda.model.geometry import ROTATIONS
from kohakuefda.solvers.regional.candidates import Proposals


def window_sum(mask: np.ndarray, width: int, height: int) -> np.ndarray:
    """Sum occupied cells in every fitting rectangular window."""
    prefix = np.pad(mask, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    return (
        prefix[height:, width:]
        - prefix[:-height, width:]
        - prefix[height:, :-width]
        + prefix[:-height, :-width]
    )


def endpoint_distances(
    grid: tuple[int, int], cells: tuple[tuple[int, int], ...]
) -> np.ndarray:
    """Minimum Manhattan distance to any supplied endpoint at every grid cell."""
    width, height = grid
    distance = np.full((height, width), width + height, dtype=np.int32)
    for x, y in cells:
        distance[y, x] = 0
    for axis in (0, 1):
        offsets = np.arange(distance.shape[axis], dtype=np.int32)
        if axis == 0:
            offsets = offsets[:, None]
        forward = np.minimum.accumulate(distance - offsets, axis=axis) + offsets
        reverse = np.flip(distance, axis=axis)
        backward = np.flip(
            np.minimum.accumulate(reverse - offsets, axis=axis) + offsets, axis=axis
        )
        distance = np.minimum(forward, backward)
    return distance


class Frontier(Proposals):
    """Estimate obstruction and endpoint distance for each missing free machine."""

    def potential(self) -> float:
        self.reset(0)
        ctx = self.context
        x0, y0, x1, y1 = self.area
        scores = []
        placed = dict(ctx.anchors)
        cache = {}
        distances = {}
        grid = ctx.view.grid
        for block_id, block in ctx.blocks.items():
            if block_id in placed or block.constraint != "free" or block.group:
                continue
            ctx.budget.check()
            best = 2.0
            targets = ctx.connection_targets(block_id)
            for target in targets:
                if target.cells and target.cells not in distances:
                    distances[target.cells] = endpoint_distances(grid, target.cells)
            for rotation in ROTATIONS:
                width, height = (
                    (block.width, block.height)
                    if rotation % 180 == 0
                    else (block.height, block.width)
                )
                if width > x1 - x0 or height > y1 - y0:
                    continue
                if (width, height) not in cache:
                    overlap = window_sum(self.occupied, width, height)
                    yy, xx = np.indices(overlap.shape)
                    cache[width, height] = overlap.astype(float), xx + x0, yy + y0
                overlap, xx, yy = cache[width, height]
                distance = np.zeros_like(overlap)
                for target in targets:
                    paths = (
                        [
                            distances[target.cells][yy + dy, xx + dx]
                            for dx, dy in self.ports[block_id, target.lane_id, rotation]
                        ]
                        if target.cells
                        else []
                    )
                    distance += np.minimum.reduce(paths) if paths else x1 - x0 + y1 - y0
                cost = overlap / (width * height) + distance / (
                    max(1, len(targets)) * (x1 - x0 + y1 - y0)
                )
                best = min(best, float(cost.min()))
            scores.append(best)
        return sum(scores) / max(1, len(scores))
