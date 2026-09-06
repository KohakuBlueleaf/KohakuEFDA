"""Coordinated compression and connection-directed physical-layout proposals."""

import random

from kohakuefda.model.geometry import ROTATIONS
from kohakuefda.model.solver import Action

PINNED = ("slot", "edge")


class CompactionMoves:
    """Sample compaction candidates; the framework decides physical feasibility."""

    def __init__(self, context, settings: dict, rng: random.Random) -> None:
        self.context = context
        self.settings = settings
        self.rng = rng
        self.signature = None
        self.cuts = []
        self.neighbors = {i: [] for i in context.blocks}
        for link in context.links:
            self.neighbors[link.source].append(link.sink)
            self.neighbors[link.sink].append(link.source)
        self.movable = tuple(
            i
            for i, b in context.blocks.items()
            if not b.group or b.constraint == "slot"
        )

    def cut(self) -> Action | None:
        ctx = self.context
        view = ctx.view
        signature = ctx.current.id
        if signature != self.signature:
            self.signature = signature
            self.cuts = self.cut_candidates(view)
        if not self.cuts:
            return None
        index = self.rng.randrange(
            min(len(self.cuts), self.settings["compact_choices"])
        )
        _, anchors = self.cuts.pop(index)
        placed = dict(view.anchors)
        moved = tuple((i, a) for i, a in anchors.items() if a != placed[i])
        return Action("relocate", moved)

    def cut_candidates(self, view) -> list:
        ctx = self.context
        standing = {cell for _, cells in view.footprints for cell in cells}
        candidates = {}
        for axis in (0, 1):
            lines = sorted(
                set(range(view.bbox[axis], view.bbox[axis + 2]))
                - {c[axis] for c in standing}
            )
            for line in lines:
                for direction in (-1, 1):
                    moved = {
                        i
                        for i, a in view.anchors
                        if ctx.blocks[i].constraint not in PINNED
                        and (a[axis] > line if direction == -1 else a[axis] < line)
                    }
                    if not moved:
                        continue
                    anchors = {
                        i: tuple(
                            value + direction if k == axis and i in moved else value
                            for k, value in enumerate(a)
                        )
                        for i, a in view.anchors
                    }
                    key = tuple(sorted(anchors.items()))
                    if key in candidates:
                        continue
                    cells = [
                        (
                            (
                                x + (direction if axis == 0 else 0),
                                y + (direction if axis == 1 else 0),
                            )
                            if i in moved
                            else (x, y)
                        )
                        for i, owned in view.footprints
                        for x, y in owned
                    ]
                    width = max(x for x, y in cells) - min(x for x, y in cells) + 1
                    height = max(y for x, y in cells) - min(y for x, y in cells) + 1
                    wire = sum(
                        abs(anchors[l.source][0] - anchors[l.sink][0])
                        + abs(anchors[l.source][1] - anchors[l.sink][1])
                        for l in ctx.links
                    )
                    candidates[key] = ((width * height, wire), anchors)
        return sorted(candidates.values(), key=lambda item: item[0])

    def pull(self) -> Action | None:
        ctx = self.context
        placed = dict(ctx.anchors)
        choices = [i for i in self.movable if i in placed and self.neighbors[i]]
        if not choices:
            return None
        block_id = self.rng.choice(choices)
        b = ctx.blocks[block_id]
        x, y, r = placed[block_id]
        if b.constraint == "slot":
            anchors = ctx.slot_anchors(block_id)
        elif b.constraint == "edge":
            anchors = ctx.border_anchors()
        else:
            radius = self.settings["pull_radius"]
            anchors = [
                (x + dx, y + dy, rotation)
                for dx in range(-radius, radius + 1)
                for dy in range(-radius, radius + 1)
                for rotation in (r,)
                if dx or dy
            ]
        occupied = {
            c for i, cells in ctx.view.footprints if i != block_id for c in cells
        }
        x0, y0, x1, y1 = ctx.area
        partners = [placed[i] for i in self.neighbors[block_id]]
        candidates = []
        for anchor in anchors:
            if anchor == placed[block_id]:
                continue
            ax, ay, rotation = anchor
            cells = [
                (ax + dx, ay + dy) for dx, dy in b.footprints[ROTATIONS.index(rotation)]
            ]
            if any(
                not (x0 <= cx < x1 and y0 <= cy < y1) or (cx, cy) in occupied
                for cx, cy in cells
            ):
                continue
            distance = sum(abs(ax - px) + abs(ay - py) for px, py, _ in partners)
            candidates.append((distance, anchor))
        candidates.sort()
        if not candidates:
            return None
        _, anchor = self.rng.choice(candidates[: self.settings["compact_choices"]])
        return Action("relocate", ((block_id, anchor),))
