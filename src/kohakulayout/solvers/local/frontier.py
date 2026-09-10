"""An optimistic potential for what is still missing: obstruction and distance to the pins it must reach."""

import numpy as np

from kohakulayout.ir.geometry import XY, rotate_size
from kohakulayout.solvers.regional.candidates import Proposals, is_free


def window_sum(mask: np.ndarray, width: int, height: int) -> np.ndarray:
    """Occupied cells in every fitting ``width x height`` window."""
    prefix = np.pad(mask, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    return (
        prefix[height:, width:]
        - prefix[:-height, width:]
        - prefix[height:, :-width]
        + prefix[:-height, :-width]
    )


def endpoint_distances(width: int, height: int, cells: tuple[XY, ...]) -> np.ndarray:
    """Manhattan distance to the nearest of ``cells`` at every grid cell."""
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
    """Mean over missing free cells of the cheapest window: overlap fraction plus normalised pin distance."""

    def potential(self) -> float:
        self.reset(0)
        world = self.world
        span = self.width + self.height
        scores: list[float] = []
        cache: dict[tuple[int, int], tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
        distances: dict[tuple[XY, ...], np.ndarray] = {}
        for cell_id, cell in world.netlist.cells.items():
            if cell_id in world.placements or not is_free(cell):
                continue
            fp = world.footprint_of(cell_id)
            targets = self.targets(cell_id)
            for _, cells in targets:
                key = tuple(cells)
                if key not in distances:
                    distances[key] = endpoint_distances(self.width, self.height, key)
            best = 2.0
            for rot in fp.rotations:
                w, h = rotate_size(fp.width, fp.height, rot)
                if w > self.width or h > self.height:
                    continue
                if (w, h) not in cache:
                    overlap = window_sum(self.occupied, w, h)
                    yy, xx = np.indices(overlap.shape)
                    cache[w, h] = overlap.astype(float), xx, yy
                overlap, xx, yy = cache[w, h]
                distance = np.zeros_like(overlap)
                offsets = self.offsets(cell_id, rot)
                for pin_id, cells in targets:
                    offset = offsets.get(pin_id)
                    if offset is None:
                        distance += span
                        continue
                    table = distances[tuple(cells)]
                    px = np.clip(xx + offset[0], 0, self.width - 1)
                    py = np.clip(yy + offset[1], 0, self.height - 1)
                    distance += table[py, px]
                cost = overlap / (w * h) + distance / (max(1, len(targets)) * span)
                best = min(best, float(cost.min()))
            scores.append(best)
        return sum(scores) / max(1, len(scores))


__all__ = ["Frontier", "endpoint_distances", "window_sum"]
