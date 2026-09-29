"""The project's construction and repair search on the framework's regional search.

``EndfieldSearch`` builds the regional seed: unwired cells first, then cells with a
placed lane neighbour, each pulled toward its place in a force-directed embedding of
the lane graph. ``GuidedSearch`` repairs a layout: anchors scored by a distinct-port
assignment against the lane router's targets, the repaired region grown around the
endpoints recent refusals name.
"""

import random
from collections import Counter
from typing import Any

import numpy as np

from kohakuefda.layout.router import LanePolicy, lane_ends
from kohakuefda.physics.boundaries import CLUSTER, PART_KIND, SEAT
from kohakuefda.physics.facts import lane_facts
from kohakulayout.ir import PinRef
from kohakulayout.ir.geometry import ROTATIONS, XY, footprint_cells
from kohakulayout.solvers.regional.candidates import Proposals, is_free
from kohakulayout.solvers.regional.contact import ContactProposals
from kohakulayout.solvers.regional.search import DEFAULTS as FRAMEWORK_DEFAULTS
from kohakulayout.solvers.regional.search import Search

EMBED_STEPS = 300
RESEATED = frozenset({SEAT, "slot"})
DEFAULTS: dict[str, Any] = {
    **{k: v for k, v in FRAMEWORK_DEFAULTS.items() if k != "origin_weight"},
    "center_weight": 0.2,
    "depot_step": 2,
    "depot_window": 20,
    "extent_weight": 0.0,
    "insert_failures": 16,
    "net_failures": 0,
    "embed_weight": 0.3,
    "lookahead": 1,
}
GUIDED: dict[str, Any] = {
    **DEFAULTS,
    "gap": 0,
    "gap_cycle": 2,
    "candidates": 80,
    "insert_failures": 24,
    "extent_weight": 0.05,
    "embed_weight": 0.0,
    "alignment_weight": 0.25,
    "blocked_cost": 1000.0,
    "candidate_bucket": 3,
    "bucket_quota": 2,
    "jitter": 2.0,
    "conflict_window": 64,
    "conflict_size": 8,
    "corner_weight": 0.03,
}


def embed(
    pairs: list[tuple[str, str]], box: tuple[int, int, int, int]
) -> dict[str, XY]:
    """A place in the box for every cell of ``pairs``: a force-directed layout of the
    lane graph (springs along lanes, repulsion between all) scaled into the box with a
    tenth for margin; deterministic in the pairs."""
    names = sorted({c for pair in pairs for c in pair})
    if not names:
        return {}

    index = {c: i for i, c in enumerate(names)}
    n = len(names)
    edges = np.array([[index[a], index[b]] for a, b in pairs if a != b], dtype=int)
    angles = np.arange(n) * (2 * np.pi / n)
    pos = np.stack([np.cos(angles), np.sin(angles)], axis=1) * n
    for step in range(EMBED_STEPS):
        delta = pos[:, None, :] - pos[None, :, :]
        dist = np.maximum(np.sqrt((delta**2).sum(axis=2)), 1e-3)
        force = (
            delta / dist[:, :, None] * np.minimum(1.0 / dist, 1.0)[:, :, None]
        ).sum(axis=1) * n
        if len(edges):
            span = pos[edges[:, 0]] - pos[edges[:, 1]]
            np.add.at(force, edges[:, 0], -span * 0.1)
            np.add.at(force, edges[:, 1], span * 0.1)
        pos += force * (0.5 * (1 - step / EMBED_STEPS) + 0.02)

    x0, y0, x1, y1 = box
    mx, my = (x1 - x0) * 0.1, (y1 - y0) * 0.1
    low, high = pos.min(axis=0), pos.max(axis=0)
    unit = (pos - low) / np.where(high - low > 0, high - low, 1.0)
    return {
        c: (
            float(x0 + mx + unit[i, 0] * (x1 - x0 - 2 * mx)),
            float(y0 + my + unit[i, 1] * (y1 - y0 - 2 * my)),
        )
        for c, i in index.items()
    }


class EndfieldProposals(Proposals):
    """Anchors ranked toward the lane router's targets: the first cells pulled to a third
    of the area, the rest to its corner, laned cells toward their embedded place; a free
    depot part with no placed mate on a lattice in the origin corner."""

    def ranked(self, cell_id: str, trial: int, rng: Any) -> list[Any]:
        self.ranking = cell_id
        return super().ranked(cell_id, trial, rng)

    @property
    def places(self) -> dict[str, XY]:
        found = getattr(self, "_places", None)
        if found is None:
            netlist = self.world.netlist
            pairs = [
                (s, t)
                for net in netlist.nets.values()
                for (s, _), (t, _), _ in lane_facts(net)
                if netlist.cells[s].kind != PART_KIND
                and netlist.cells[t].kind != PART_KIND
            ]
            found = self._places = embed(pairs, self.box)
        return found

    @property
    def policy(self) -> Any:
        found = getattr(self.world.router, "policy", None)
        return found if found is not None else LanePolicy()

    def pull(self, array: np.ndarray, first: bool) -> np.ndarray:
        x0, y0, x1, y1 = self.box
        ranking = getattr(self, "ranking", None)
        if first and self.world.placements and ranking is not None:
            first = self.world.netlist.cells[ranking].kind != PART_KIND

        if first:
            cx, cy = x0 + (x1 - x0) // 3, y0 + (y1 - y0) // 3
            out = self.settings["center_weight"] * (
                np.abs(array[:, 0] - cx) + np.abs(array[:, 1] - cy)
            )
        else:
            out = self.settings["corner_weight"] * (array[:, 0] - x0 + array[:, 1] - y0)

        place = self.places.get(ranking) if ranking is not None else None
        weight = self.settings["embed_weight"]
        if place is None or not weight:
            return out

        fp = self.world.footprint_of(ranking)
        tx = place[0] - (fp.width - 1) / 2 if fp is not None else place[0]
        ty = place[1] - (fp.height - 1) / 2 if fp is not None else place[1]
        return out + weight * (np.abs(array[:, 0] - tx) + np.abs(array[:, 1] - ty))

    def attach_clear(self, clear: np.ndarray, cell_id: str, rot: int) -> np.ndarray:
        return clear

    def fitting(self, cell_id: str) -> np.ndarray:
        world = self.world
        cell = world.netlist.cells[cell_id]
        group = world.netlist.groups[cell.group] if cell.group is not None else None
        mates = [
            m
            for m in (group.members if group is not None else ())
            if m in world.placements and m != cell_id
        ]
        loose = cell.constraint.kind in ("free", CLUSTER)
        if cell.kind != PART_KIND or not loose or mates:
            return super().fitting(cell_id)

        fp = world.footprint_of(cell_id)
        x0, y0, _, _ = self.box
        step, window = self.settings["depot_step"], self.settings["depot_window"]
        rows = [
            (x0 + dx, y0 + dy, rot)
            for dy in range(step, window, step)
            for dx in range(step, window, step)
            for rot in ROTATIONS
            if fp is None or rot in fp.rotations
        ]
        return np.array(rows, dtype=int) if rows else np.zeros((0, 3), dtype=int)

    def reset(self, gap: int) -> None:
        """The clearance map of placed footprints and their gap only, so a window may
        cross a lane its footprint would displace."""
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

    def targets(self, cell_id: str) -> list[tuple[str, list[XY]]]:
        """One entry per lane with a placed partner: the cells the lane router would open
        on the partner pin's own lanes, else every attach cell the partner pin may use.
        """
        world = self.world
        out: list[tuple[str, list[XY]]] = []
        for net in world.netlist.nets.values():
            wire = world.wires.get(net.id)
            for (source, source_pin), (sink, sink_pin), _ in lane_facts(net):
                if cell_id == source:
                    mine, other, other_pin = source_pin, sink, sink_pin
                elif cell_id == sink:
                    mine, other, other_pin = sink_pin, source, source_pin
                else:
                    continue
                if other not in world.placements:
                    continue

                cells = None
                if wire is not None:
                    partner = PinRef(cell=other, pin=other_pin)
                    towards = 0 if cell_id == sink else 1
                    cells = lane_ends(world, net, partner, towards, self.policy)
                if cells is None:
                    cells = {xy for _, xy in world.open_ports(other, other_pin)}
                out.append((mine, sorted(cells)))
        return out


class EndfieldSearch(Search):
    """The regional seed: its jitter from the raw seed over the declared cell order,
    unwired cells first, then cells with a placed lane neighbour."""

    defaults = DEFAULTS
    proposer = EndfieldProposals
    reseated = RESEATED

    def __init__(self, ctx: Any, settings: dict[str, Any] | None = None) -> None:
        super().__init__(ctx, settings)
        self.rng = random.Random(ctx.seed)
        declared = ctx.problem.netlist.cells
        if set(declared) == set(self.cells):
            self.cells = declared

    @staticmethod
    def neighbourhood(netlist: Any) -> dict[str, list[str]]:
        """A lane's two ends are neighbours, once per lane."""
        out: dict[str, list[str]] = {c: [] for c in netlist.cells}
        for net in netlist.nets.values():
            for (source, _), (sink, _), _ in lane_facts(net):
                out[source].append(sink)
                out[sink].append(source)
        return out

    def priority(self, cell_id: str, placed: Any, jitter: dict[str, float]) -> tuple:
        n = sum(j in placed for j in self.neighbours[cell_id])
        fp = self.world.footprint_of(cell_id)
        return (
            not self.world.netlist.pins_of(cell_id),
            n > 0,
            self.pressure[cell_id] + n / (len(self.neighbours[cell_id]) or 1),
            n,
            fp.width * fp.height,
            jitter[cell_id],
        )


class GuidedProposals(ContactProposals, EndfieldProposals):
    """Contact scoring against the project's lane targets, pulled to the area's corner."""

    def pull(self, anchors: np.ndarray, first: bool) -> np.ndarray:
        x0, y0, _, _ = self.box
        return self.settings["corner_weight"] * (
            anchors[:, 0] - x0 + anchors[:, 1] - y0
        )


class GuidedSearch(EndfieldSearch):
    """Repair around the endpoints the last ``conflict_window`` refusals name, every
    fourth trial the framework's region instead."""

    defaults = GUIDED
    proposer = GuidedProposals

    def region(self, trial: int) -> set[str]:
        placed = self.world.placements
        free = {c for c in placed if is_free(self.cells[c])}
        pressure: Counter[str] = Counter()
        window = int(self.settings["conflict_window"])
        for refusal in self.ctx.refusals[-window:] if window else ():
            prefix, _, name = refusal.subject.partition(":")
            if prefix == "net" and name in self.world.netlist.nets:
                pressure.update(r.cell for r in self.world.netlist.nets[name].pins())
            elif prefix == "cell":
                pressure[name] += 1

        candidates = sorted(free.intersection(pressure))
        if not candidates or trial % 4 == 0:
            return super().region(trial)

        pivot = max(candidates, key=lambda c: (pressure[c], c))
        anchor = placed[pivot]
        related = set(self.neighbours[pivot])
        ranked = sorted(
            free,
            key=lambda c: (
                abs(placed[c].x - anchor.x)
                + abs(placed[c].y - anchor.y)
                - 4 * (c in related)
                - 2 * min(pressure[c], 4),
                c,
            ),
        )
        return set(ranked[: int(self.settings["conflict_size"])])


__all__ = [
    "DEFAULTS",
    "GUIDED",
    "RESEATED",
    "EndfieldProposals",
    "EndfieldSearch",
    "GuidedProposals",
    "GuidedSearch",
    "embed",
]
