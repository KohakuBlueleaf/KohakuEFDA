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
    "center_weight": 0.2,
    "corner_weight": 0.015,
    "group_radius": 2,
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
        self._offsets: dict[tuple[str, int], dict[str, XY]] = {}
        outside = np.ones((self.height, self.width), dtype=np.int8)
        for x, y in world.build_cells:
            outside[y, x] = 0
        self.outside = outside

    # ------------------------------------------------------------ the map
    def reset(self, gap: int) -> None:
        self.gap = gap
        self.occupied[:] = self.outside
        for cell_id, placement in self.world.placements.items():
            self.occupy(cell_id, placement.x, placement.y, placement.rot)

    def occupy(self, cell_id: str, x: int, y: int, rot: int) -> None:
        fp = self.world.footprint_of(cell_id)
        if fp is None:
            return
        for cx, cy in footprint_cells(x, y, fp.width, fp.height, rot):
            if 0 <= cx < self.width and 0 <= cy < self.height:
                self.occupied[
                    max(0, cy - self.gap) : cy + self.gap + 1,
                    max(0, cx - self.gap) : cx + self.gap + 1,
                ] = 1

    def offsets(self, cell_id: str, rot: int) -> dict[str, XY]:
        """Each pin's attach cell relative to the anchor, for one rotation."""
        fp = self.world.footprint_of(cell_id)
        key = (fp.id, rot)
        found = self._offsets.get(key)
        if found is None:
            found = {}
            for pin in self.world.netlist.pins_of(cell_id):
                port = fp.port(pin.ports[0]) if pin.ports else None
                if port is not None:
                    found[pin.id] = attach_cell(
                        fp.width, fp.height, port.side, port.offset, rot
                    )
            self._offsets[key] = found
        return found

    # ------------------------------------------------------------ anchors
    def fitting(self, cell_id: str) -> list[Anchor]:
        """Anchors the pack allows for a constrained cell, near its group, or every clear window."""
        world = self.world
        cell = world.netlist.cells[cell_id]
        fp = world.footprint_of(cell_id)
        if cell.constraint.kind != "free":
            return list(world.anchors(cell_id))
        if cell.group is not None:
            members = [
                m
                for m in world.netlist.groups[cell.group].members
                if m in world.placements and m != cell_id
            ]
            if members:
                return self.group_window(cell_id, members)
        integral = np.pad(self.occupied, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
        out: list[Anchor] = []
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
            yy, xx = np.nonzero(blocked == 0)
            out.extend(
                Anchor(x=int(x), y=int(y), rot=rot) for x, y in zip(xx, yy, strict=True)
            )
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

    def targets(self, cell_id: str) -> dict[str, list[XY]]:
        """Per own pin, the attach cells of the placed pins on the other ends of its nets."""
        world = self.world
        out: dict[str, list[XY]] = {}
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
                        out.setdefault(pin_id, []).append(attach)
        return out

    def ranked(self, cell_id: str, trial: int, rng: random.Random) -> list[Anchor]:
        """The best ``candidates`` anchors: pins close to their targets, a centre pull for the first cells, jitter by trial."""
        anchors = self.fitting(cell_id)
        if not anchors:
            return []
        targets = self.targets(cell_id)
        array = np.array([(a.x, a.y, a.rot) for a in anchors])
        score = np.zeros(len(anchors))
        for rot in {a.rot for a in anchors}:
            mask = array[:, 2] == rot
            subset = array[mask]
            offsets = self.offsets(cell_id, rot)
            values = np.zeros(len(subset), dtype=float)
            for pin_id, cells in targets.items():
                offset = offsets.get(pin_id)
                if offset is None:
                    values += self.settings["closed_cost"]
                    continue
                distances = [
                    np.abs(subset[:, 0] + offset[0] - tx)
                    + np.abs(subset[:, 1] + offset[1] - ty)
                    for tx, ty in cells
                ]
                values += np.minimum.reduce(distances)
            score[mask] = values
        if not self.world.placements or not targets:
            score += self.settings["center_weight"] * (
                np.abs(array[:, 0] - self.width // 3)
                + np.abs(array[:, 1] - self.height // 3)
            )
        else:
            score += self.settings["corner_weight"] * (array[:, 0] + array[:, 1])
        if trial:
            noise = np.random.default_rng(rng.randrange(2**32))
            score += noise.uniform(0, self.settings["jitter"] + trial % 4, len(score))
        order = np.argsort(score, kind="stable")[: self.settings["candidates"]]
        return [anchors[int(i)] for i in order]


__all__ = ["DEFAULTS", "Proposals", "is_free"]
