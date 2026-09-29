"""Port-aware contact proposals for grid placement, without a row constraint."""

import random
from typing import Any

import numpy as np

from kohakulayout.ir.geometry import attach_cell, rotate_size
from kohakulayout.physics.protocol import Anchor
from kohakulayout.solvers.regional.assignment import distinct_cost
from kohakulayout.solvers.regional.candidates import Proposals

BLOCKED_COST = 1000.0
BUCKET_SIZE = 3
BUCKET_QUOTA = 2
ALIGN_WEIGHT = 0.25


class ContactProposals(Proposals):
    """Rank fitting anchors by distinct pin assignment, compactness and edge alignment."""

    def physical_map(self) -> np.ndarray:
        """Footprint occupancy only; displaced wires and support units remain negotiable."""
        occupied = np.zeros((self.height, self.width), dtype=bool)
        for cell_id, placement in self.world.placements.items():
            fp = self.world.footprint_of(cell_id)
            if fp is None:
                continue
            width, height = rotate_size(fp.width, fp.height, placement.rot)
            x, y = placement.x, placement.y
            occupied[max(0, y) : y + height, max(0, x) : x + width] = True
        return occupied

    def pin_costs(
        self,
        cell_id: str,
        rot: int,
        anchors: np.ndarray,
        targets: list[Any],
        occupied: np.ndarray,
    ) -> np.ndarray:
        """All pins choose distinct attachment points; existing partners contribute distance."""
        fp = self.world.footprint_of(cell_id)
        by_pin: dict[str, list[Any]] = {}
        for pin_id, cells in targets:
            by_pin.setdefault(pin_id, []).append(cells)
        groups: dict[str, list[dict[str, np.ndarray]]] = {}
        for pin in self.world.netlist.pins_of(cell_id):
            options: dict[str, np.ndarray] = {}
            for port_id in pin.ports:
                port = fp.port(port_id)
                if port is None:
                    continue
                ox, oy = attach_cell(fp.width, fp.height, port.side, port.offset, rot)
                xx, yy = anchors[:, 0] + ox, anchors[:, 1] + oy
                inside = (xx >= 0) & (yy >= 0) & (xx < self.width) & (yy < self.height)
                blocked = ~inside
                blocked[inside] |= occupied[yy[inside], xx[inside]]
                value = blocked.astype(float) * self.settings.get(
                    "blocked_cost", BLOCKED_COST
                )
                for cells in by_pin.get(pin.id, ()):
                    if not cells:
                        value += self.settings["closed_cost"]
                        continue
                    nearest = np.full(len(anchors), np.inf)
                    for tx, ty in cells:
                        np.minimum(
                            nearest, np.abs(xx - tx) + np.abs(yy - ty), out=nearest
                        )
                    value += nearest
                options[port_id] = value
            groups.setdefault(pin.carrier, []).append(options)
        return sum(
            (distinct_cost(group, len(anchors)) for group in groups.values()),
            np.zeros(len(anchors)),
        )

    def alignment(self, cell_id: str, anchors: np.ndarray) -> np.ndarray:
        """Distance to the nearest parallel edge of a similarly sized placed footprint."""
        fp = self.world.footprint_of(cell_id)
        peers = [
            p
            for key, p in self.world.placements.items()
            if self.world.footprint_of(key) is not None
            and self.world.footprint_of(key).width == fp.width
            and self.world.footprint_of(key).height == fp.height
        ]
        if not peers:
            return np.zeros(len(anchors))
        distance = np.full(len(anchors), np.inf)
        for peer in peers:
            offset = np.minimum(
                np.abs(anchors[:, 0] - peer.x), np.abs(anchors[:, 1] - peer.y)
            )
            np.minimum(distance, offset, out=distance)
        return distance * self.settings.get("alignment_weight", ALIGN_WEIGHT)

    def ranked(self, cell_id: str, trial: int, rng: random.Random) -> list[Anchor]:
        """Score all fitting anchors, then retain spatially diverse low-cost alternatives."""
        anchors = self.fitting(cell_id)
        if not len(anchors):
            return []
        targets = self.targets(cell_id)
        occupied = self.physical_map()
        extent = self.extent()
        fp = self.world.footprint_of(cell_id)
        score = np.zeros(len(anchors))
        for rot in np.unique(anchors[:, 2]).tolist():
            mask = anchors[:, 2] == rot
            subset = anchors[mask]
            value = self.pin_costs(cell_id, rot, subset, targets, occupied)
            if extent is not None:
                width, height = rotate_size(fp.width, fp.height, rot)
                value += self.settings["extent_weight"] * self.growth(
                    extent, subset, width, height
                )
            score[mask] = value
        score += self.pull(anchors, not self.world.placements or not targets)
        score += self.alignment(cell_id, anchors)
        if trial:
            noise = np.random.default_rng(rng.randrange(2**32))
            score += noise.uniform(0, self.settings["jitter"], len(score))
        size = max(1, self.settings.get("candidate_bucket", BUCKET_SIZE))
        quota = max(1, self.settings.get("bucket_quota", BUCKET_QUOTA))
        buckets: dict[tuple[int, int, int], int] = {}
        chosen: list[Anchor] = []
        for index in np.argsort(score, kind="stable"):
            if not np.isfinite(score[index]):
                continue
            x, y, rot = (int(v) for v in anchors[index])
            key = (x // size, y // size, rot)
            if buckets.get(key, 0) >= quota:
                continue
            buckets[key] = buckets.get(key, 0) + 1
            chosen.append(Anchor(x=x, y=y, rot=rot))
            if len(chosen) >= self.settings["candidates"]:
                break
        return chosen


__all__ = [
    "ALIGN_WEIGHT",
    "BLOCKED_COST",
    "BUCKET_QUOTA",
    "BUCKET_SIZE",
    "ContactProposals",
]
