"""Target-directed relocation, coordinated cuts and existing coupled repair proposals."""

import numpy as np

from kohakuefda.framework.workspace import outside_distance
from kohakuefda.model.solver import Action
from kohakuefda.solvers.local.frontier import endpoint_distances
from kohakuefda.solvers.local.moves import LayoutMoves
from kohakuefda.solvers.regional import DEFAULTS as REGIONAL_DEFAULTS
from kohakuefda.solvers.regional.candidates import Proposals


class OutlineMoves(LayoutMoves):
    """Bias physical edits toward the real outline without reducing the workspace."""

    def __init__(self, context, settings, target):
        super().__init__(context, settings)
        self.target = target
        self.positions = Proposals(context, REGIONAL_DEFAULTS)
        self.operators = (
            *self.operators,
            self.inward,
            self.inward,
            self.inward,
            self.squeeze,
            self.squeeze,
            self.infill,
            self.infill,
        )

    def inward(self):
        ctx = self.context
        footprints = dict(ctx.view.footprints)
        scores = sorted(
            (
                (sum(outside_distance(c, self.target) for c in footprints[i]), i)
                for i in self.free
            ),
            reverse=True,
        )
        if not scores:
            return None
        _, i = self.rng.choice(scores[: self.settings["compact_choices"]])
        x, y, r = dict(ctx.anchors)[i]
        block = ctx.blocks[i]
        width, height = (
            (block.width, block.height) if r % 180 == 0 else (block.height, block.width)
        )
        tx = min(self.target[2] - width - 1, max(self.target[0] + 1, x))
        ty = min(self.target[3] - height - 1, max(self.target[1] + 1, y))
        radius = self.settings["outline_radius"]
        candidates = [
            (abs(ax - tx) + abs(ay - ty), (ax, ay, r))
            for ax in range(x - radius, x + radius + 1)
            for ay in range(y - radius, y + radius + 1)
            if (ax, ay) != (x, y)
        ]
        occupied = {c for j, cells in footprints.items() if i != j for c in cells}
        x0, y0, x1, y1 = ctx.area
        valid = [
            (score, anchor)
            for score, anchor in candidates
            if all(
                x0 <= anchor[0] + dx < x1
                and y0 <= anchor[1] + dy < y1
                and (anchor[0] + dx, anchor[1] + dy) not in occupied
                for dx, dy in block.footprints[r // 90]
            )
        ]
        if not valid:
            return None
        valid.sort()
        _, anchor = self.rng.choice(valid[: self.settings["compact_choices"]])
        return Action("relocate", ((i, anchor),))

    def infill(self):
        ctx = self.context
        footprints = dict(ctx.view.footprints)
        outside = [
            i
            for i in self.free
            if any(outside_distance(c, self.target) for c in footprints[i])
        ]
        if not outside:
            return None
        block_id = self.rng.choice(outside)
        block = ctx.blocks[block_id]
        self.positions.reset(0)
        anchors = self.positions.anchors(block_id)
        if not anchors:
            return None
        array = np.array(anchors)
        scores = np.zeros(len(anchors))
        overflow = np.zeros(len(anchors))
        targets = ctx.connection_targets(block_id)
        grid = ctx.view.grid
        distances = {
            t.cells: endpoint_distances(grid, t.cells) for t in targets if t.cells
        }
        for rotation in (0, 90, 180, 270):
            mask = array[:, 2] == rotation
            subset = array[mask]
            width, height = (
                (block.width, block.height)
                if rotation % 180 == 0
                else (block.height, block.width)
            )
            x0, y0, x1, y1 = self.target
            overflow[mask] = (
                np.maximum(x0 - subset[:, 0], 0)
                + np.maximum(subset[:, 0] + width - x1, 0)
                + np.maximum(y0 - subset[:, 1], 0)
                + np.maximum(subset[:, 1] + height - y1, 0)
            )
            values = np.zeros(len(subset))
            for target in targets:
                if not target.cells:
                    continue
                ports = self.positions.ports[block_id, target.lane_id, rotation]
                if ports:
                    values += np.minimum.reduce(
                        [
                            distances[target.cells][
                                subset[:, 1] + dy, subset[:, 0] + dx
                            ]
                            for dx, dy in ports
                        ]
                    )
            scores[mask] = values
        indices = np.lexsort((np.arange(len(anchors)), scores, overflow))[
            : self.settings["compact_choices"]
        ]
        anchor = anchors[int(self.rng.choice(indices))]
        return Action("relocate", ((block_id, anchor),))

    def squeeze(self):
        ctx = self.context
        placed = dict(ctx.anchors)
        axis = self.rng.randrange(2)
        line = self.rng.randint(self.target[axis], self.target[axis + 2] - 1)
        moved = {
            i
            for i, anchor in placed.items()
            if anchor[axis] > line and ctx.blocks[i].constraint == "free"
        }
        if not moved:
            return None
        anchors = tuple(
            (i, tuple(v - (1 if k == axis else 0) for k, v in enumerate(placed[i])))
            for i in sorted(moved)
        )
        footprints = dict(ctx.view.footprints)
        occupied = {
            c for i, cells in footprints.items() if i not in moved for c in cells
        }
        for i, _ in anchors:
            for cell in footprints[i]:
                shifted = tuple(v - (1 if k == axis else 0) for k, v in enumerate(cell))
                if shifted in occupied:
                    return None
        return Action("relocate", anchors)
