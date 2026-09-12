"""Anchor proposals: every fitting window on a clearance map, ranked by distance to the pins they must reach."""

import random
from typing import Any

import numpy as np

from kohakulayout.ir.geometry import XY, attach_cell, footprint_cells, rotate_size
from kohakulayout.physics.protocol import Anchor

DEFAULTS: dict[str, Any] = {
    "candidates": 150,
    "gap": 2,
    "jitter": 3.0,
    "closed_cost": 10000,
    "origin_weight": 0.2,
    "corner_weight": 0.015,
    "extent_weight": 1.0,
    "group_radius": 2,
    "ring": 0,
}


def is_free(cell: Any) -> bool:
    return cell.constraint.kind == "free" and cell.group is None


class Proposals:
    """A construction-time clearance map over the world and the ranking every constructor shares."""

    def __init__(self, world: Any, settings: dict[str, Any] | None = None) -> None:
        self.world = world
        self.settings = {**DEFAULTS, **(settings or {})}
        self.width, self.height = world.fabric.width, world.fabric.height
        self.occupied = np.zeros((self.height, self.width), dtype=np.int8)
        self.gap = 0
        self._offsets: dict[tuple[str, int], dict[str, tuple[XY, ...]]] = {}
        outside = np.ones((self.height, self.width), dtype=np.int8)
        for x, y in world.build_cells:
            outside[y, x] = 0
        self.outside = outside
        xs = [x for x, _ in world.build_cells] or [0, self.width - 1]
        ys = [y for _, y in world.build_cells] or [0, self.height - 1]
        self.box = (min(xs), min(ys), max(xs) + 1, max(ys) + 1)

    # ------------------------------------------------------------ the map
    def reset(self, gap: int) -> None:
        """Rebuild the map: outside cells, placed footprints with their gap, wires, and every open attach ring."""
        self.gap = gap
        self.occupied[:] = self.outside
        for cell_id, placement in self.world.placements.items():
            self.occupy(cell_id, placement.x, placement.y, placement.rot)
        for layer in self.world.fabric.layers:
            for x, y in self.world.kernel.holders_map(layer):
                if 0 <= x < self.width and 0 <= y < self.height:
                    self.occupied[y, x] = 1
        for owners in self.world.open_attach_owners().values():
            for x, y in owners:
                self.ring(x, y)

    def ring(self, x: int, y: int) -> None:
        """An attach cell, and its neighbours when ``ring`` is 1: where a wire must be free to leave."""
        spots = (
            [(0, 0)]
            if not self.settings.get("ring")
            else [(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)]
        )
        for dx, dy in spots:
            cx, cy = x + dx, y + dy
            if 0 <= cx < self.width and 0 <= cy < self.height:
                self.occupied[cy, cx] = 1

    def occupy(self, cell_id: str, x: int, y: int, rot: int) -> None:
        """A placed footprint with its gap, and the attach cells its pins need free."""
        fp = self.world.footprint_of(cell_id)
        if fp is None:
            return
        for cx, cy in footprint_cells(x, y, fp.width, fp.height, rot):
            if 0 <= cx < self.width and 0 <= cy < self.height:
                self.occupied[
                    max(0, cy - self.gap) : cy + self.gap + 1,
                    max(0, cx - self.gap) : cx + self.gap + 1,
                ] = 1
        for ax, ay in self.offsets(cell_id, rot).values():
            self.ring(x + ax, y + ay)

    def port_offsets(self, cell_id: str, rot: int) -> dict[str, tuple[XY, ...]]:
        """Each pin's attach cells relative to the anchor, one per port it may use, for one rotation; kept per cell, since two cells of one footprint may carry different pins."""
        fp = self.world.footprint_of(cell_id)
        key = (cell_id, rot)
        found = self._offsets.get(key)
        if found is None:
            found = {}
            for pin in self.world.netlist.pins_of(cell_id):
                cells = tuple(
                    attach_cell(fp.width, fp.height, port.side, port.offset, rot)
                    for port in (fp.port(p) for p in pin.ports)
                    if port is not None
                )
                if cells:
                    found[pin.id] = cells
            self._offsets[key] = found
        return found

    def offsets(self, cell_id: str, rot: int) -> dict[str, XY]:
        """Each pin's first attach cell relative to the anchor, for one rotation."""
        return {
            pin_id: cells[0]
            for pin_id, cells in self.port_offsets(cell_id, rot).items()
        }

    # ------------------------------------------------------------ anchors
    def fitting(self, cell_id: str) -> np.ndarray:
        """Anchors as rows of ``(x, y, rot)``: the pack's for a constrained cell, near its group, or every clear window."""
        world = self.world
        cell = world.netlist.cells[cell_id]
        fp = world.footprint_of(cell_id)
        if cell.constraint.kind != "free":
            return _rows(world.anchor_rows(cell_id))
        if cell.group is not None:
            members = [
                m
                for m in world.netlist.groups[cell.group].members
                if m in world.placements and m != cell_id
            ]
            if members:
                return _rows(
                    (a.x, a.y, a.rot) for a in self.group_window(cell_id, members)
                )
        integral = np.pad(self.occupied, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
        parts: list[np.ndarray] = []
        for rot in fp.rotations:
            w, h = rotate_size(fp.width, fp.height, rot)
            if h > self.height or w > self.width:
                continue
            blocked = (
                integral[h:, w:]
                - integral[:-h, w:]
                - integral[h:, :-w]
                + integral[:-h, :-w]
            )
            clear = self.attach_clear(blocked == 0, cell_id, rot)
            yy, xx = np.nonzero(clear)
            parts.append(np.column_stack((xx, yy, np.full(len(xx), rot))))
        return np.concatenate(parts) if parts else np.zeros((0, 3), dtype=int)

    def attach_clear(self, clear: np.ndarray, cell_id: str, rot: int) -> np.ndarray:
        """The windows whose own first attach cells are clear as well; a subclass may keep every window."""
        for ax, ay in self.offsets(cell_id, rot).values():
            clear &= self.shifted_free(ax, ay, clear.shape)
        return clear

    def shifted_free(self, ax: int, ay: int, shape: tuple[int, ...]) -> np.ndarray:
        """For every anchor position, whether the cell at offset ``(ax, ay)`` is inside the grid and clear."""
        rows, cols = shape
        out = np.zeros((rows, cols), dtype=bool)
        y0, y1 = max(0, -ay), min(rows, self.height - ay)
        x0, x1 = max(0, -ax), min(cols, self.width - ax)
        if y1 > y0 and x1 > x0:
            out[y0:y1, x0:x1] = self.occupied[y0 + ay : y1 + ay, x0 + ax : x1 + ax] == 0
        return out

    def group_window(self, cell_id: str, members: list[str]) -> list[Anchor]:
        world = self.world
        fp = world.footprint_of(cell_id)
        radius = self.settings["group_radius"] + max(fp.width, fp.height)
        xs = [world.placements[m].x for m in members]
        ys = [world.placements[m].y for m in members]
        x0, y0 = max(0, min(xs) - radius), max(0, min(ys) - radius)
        x1, y1 = min(self.width, max(xs) + radius + 1), min(
            self.height, max(ys) + radius + 1
        )
        return [
            Anchor(x=x, y=y, rot=rot)
            for rot in fp.rotations
            for y in range(y0, y1)
            for x in range(x0, x1)
            if world.free_footprint(fp, x, y, rot)
        ]

    def targets(self, cell_id: str) -> list[tuple[str, list[XY]]]:
        """Where each own pin's partners are, one entry per placed partner pin: the pin and the partner's attach cell; a pin with several partners is scored once per partner."""
        world = self.world
        out: list[tuple[str, list[XY]]] = []
        for net in world.netlist.nets.values():
            mine = [r.pin for r in net.pins() if r.cell == cell_id]
            if not mine:
                continue
            for ref in net.pins():
                if ref.cell == cell_id or ref.cell not in world.placements:
                    continue
                attach = world.attach_cell(ref.cell, ref.pin)
                if attach is not None:
                    for pin_id in mine:
                        out.append((pin_id, [attach]))
        return out

    def extent(self) -> tuple[int, int, int, int] | None:
        """The placed footprints' bounding box as ``(x0, y0, x1, y1)`` inclusive, or None when nothing stands."""
        box: list[int] | None = None
        for cell_id, p in self.world.placements.items():
            fp = self.world.footprint_of(cell_id)
            if fp is None:
                continue
            w, h = rotate_size(fp.width, fp.height, p.rot)
            corners = [p.x, p.y, p.x + w - 1, p.y + h - 1]
            if box is None:
                box = corners
            else:
                box = [
                    min(box[0], corners[0]),
                    min(box[1], corners[1]),
                    max(box[2], corners[2]),
                    max(box[3], corners[3]),
                ]
        return None if box is None else (box[0], box[1], box[2], box[3])

    @staticmethod
    def growth(
        extent: tuple[int, int, int, int], subset: np.ndarray, w: int, h: int
    ) -> np.ndarray:
        """How many cells the bounding box gains for a ``w`` by ``h`` footprint at each anchor of ``subset``."""
        x0, y0, x1, y1 = extent
        nx0 = np.minimum(x0, subset[:, 0])
        ny0 = np.minimum(y0, subset[:, 1])
        nx1 = np.maximum(x1, subset[:, 0] + w - 1)
        ny1 = np.maximum(y1, subset[:, 1] + h - 1)
        return (nx1 - nx0 + 1) * (ny1 - ny0 + 1) - (x1 - x0 + 1) * (y1 - y0 + 1)

    def pull(self, array: np.ndarray, first: bool) -> np.ndarray:
        """What every anchor feels beyond its pins: a pull to the build box's origin corner, stronger for the first cells; a subclass may pull elsewhere."""
        x0, y0, _, _ = self.box
        weight = self.settings["origin_weight" if first else "corner_weight"]
        return weight * (array[:, 0] - x0 + array[:, 1] - y0)

    def ranked(self, cell_id: str, trial: int, rng: random.Random) -> list[Anchor]:
        """The best ``candidates`` anchors: pins close to their targets, a small bounding-box growth, the pull; jitter by trial."""
        array = self.fitting(cell_id)
        if len(array) == 0:
            return []
        targets = self.targets(cell_id)
        score = np.zeros(len(array))
        extent = self.extent()
        fp = self.world.footprint_of(cell_id)
        for rot in np.unique(array[:, 2]).tolist():
            mask = array[:, 2] == rot
            subset = array[mask]
            offsets = self.port_offsets(cell_id, rot)
            values = np.zeros(len(subset), dtype=float)
            if extent is not None:
                w, h = rotate_size(fp.width, fp.height, rot)
                values += self.settings["extent_weight"] * self.growth(
                    extent, subset, w, h
                )
            for pin_id, cells in targets:
                options = offsets.get(pin_id, ())
                if not options or not cells:
                    values += self.settings["closed_cost"]
                    continue
                tx = np.fromiter((c[0] for c in cells), dtype=float, count=len(cells))
                ty = np.fromiter((c[1] for c in cells), dtype=float, count=len(cells))
                nearest = None
                for ox, oy in options:
                    spans = np.abs(subset[:, 0:1] + ox - tx[None, :]) + np.abs(
                        subset[:, 1:2] + oy - ty[None, :]
                    )
                    span = spans.min(axis=1)
                    nearest = span if nearest is None else np.minimum(nearest, span)
                values += nearest
            score[mask] = values
        score += self.pull(array, not self.world.placements or not targets)
        if trial:
            noise = np.random.default_rng(rng.randrange(2**32))
            score += noise.uniform(0, self.settings["jitter"] + trial % 4, len(score))
        order = np.argsort(score, kind="stable")[: self.settings["candidates"]]
        chosen = array[order].tolist()
        return [Anchor(x=x, y=y, rot=rot) for x, y, rot in chosen]


def _rows(anchors: Any) -> np.ndarray:
    """Anchor triples as an integer array with three columns, empty ones included."""
    rows = list(anchors)
    return np.array(rows, dtype=int) if rows else np.zeros((0, 3), dtype=int)


__all__ = ["DEFAULTS", "Proposals", "is_free"]
