"""The regional construction on the framework: cells no net touches first, the first cells pulled to a third of the Core AIC Area, every cell pulled toward its place in a wirelength embedding of the lane graph, no bounding-box term, every fitting window, one routed lookahead, an insertion given up after ``INSERT_FAILURES`` refused anchors or ``NET_FAILURES`` route refusals on one net."""

import random
from typing import Any

import numpy as np

from kohakuefda.layout.router import LanePolicy, lane_ends
from kohakuefda.physics.boundaries import CLUSTER, PART_KIND
from kohakuefda.physics.facts import lane_facts
from kohakulayout.ir import PinRef
from kohakulayout.ir.geometry import ROTATIONS, XY, footprint_cells
from kohakulayout.solvers import Regional, register
from kohakulayout.solvers.protocol import Param
from kohakulayout.solvers.regional.candidates import Proposals
from kohakulayout.solvers.regional.search import DEFAULTS as FRAMEWORK_DEFAULTS
from kohakulayout.solvers.regional.search import Search

INSERT_FAILURES = 16
NET_FAILURES = 0
EMBED_WEIGHT = 0.3
EMBED_STEPS = 300

DEFAULTS: dict[str, Any] = {
    **{k: v for k, v in FRAMEWORK_DEFAULTS.items() if k != "origin_weight"},
    "center_weight": 0.2,
    "depot_step": 2,
    "depot_window": 20,
    "extent_weight": 0.0,
    "insert_failures": INSERT_FAILURES,
    "net_failures": NET_FAILURES,
    "embed_weight": EMBED_WEIGHT,
    "lookahead": 1,
}


def _param(name: str, value: Any) -> Param:
    kind = "int" if isinstance(value, int) else "float"
    return Param(name=name, type=kind, default=value)


def embed(
    pairs: list[tuple[str, str]], box: tuple[int, int, int, int]
) -> dict[str, XY]:
    """A place in the box for every cell of ``pairs``: a force-directed layout of the lane graph (springs along lanes, repulsion between all), scaled into the box with a margin; the same pairs give the same places."""
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
    scale = np.where(high - low > 0, high - low, 1.0)
    unit = (pos - low) / scale
    return {
        c: (
            float(x0 + mx + unit[i, 0] * (x1 - x0 - 2 * mx)),
            float(y0 + my + unit[i, 1] * (y1 - y0 - 2 * my)),
        )
        for c, i in index.items()
    }


class EndfieldProposals(Proposals):
    """Anchor ranking: the first cells pulled to a third of the area, the rest to its corner, every cell with lanes toward its place in the lane graph's embedding, every fitting window kept."""

    def ranked(self, cell_id: str, trial: int, rng: Any) -> list[Any]:
        self.ranking = cell_id
        return super().ranked(cell_id, trial, rng)

    @property
    def places(self) -> dict[str, XY]:
        """Every laned cell's place in the embedding, computed once."""
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

    def pull(self, array: np.ndarray, first: bool) -> np.ndarray:
        """The pull: the centre third for the first cell and for a cell with no target that is not a depot part, the corner for the rest; plus the distance to the cell's place in the embedding, when it has one."""
        x0, y0, x1, y1 = self.box
        ranking = getattr(self, "ranking", None)
        if first and self.world.placements and ranking is not None:
            first = self.world.netlist.cells[ranking].kind != PART_KIND
        if not first:
            out = self.settings["corner_weight"] * (array[:, 0] - x0 + array[:, 1] - y0)
        else:
            cx, cy = x0 + (x1 - x0) // 3, y0 + (y1 - y0) // 3
            out = self.settings["center_weight"] * (
                np.abs(array[:, 0] - cx) + np.abs(array[:, 1] - cy)
            )
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
        """The anchors: a depot part with no placed mate, free or clustering, goes on a lattice in the area's origin corner (``depot_window`` wide, every ``depot_step``); everything else as the framework fits it."""
        world = self.world
        cell = world.netlist.cells[cell_id]
        mates = (
            [
                m
                for m in world.netlist.groups[cell.group].members
                if m in world.placements and m != cell_id
            ]
            if cell.group is not None
            else []
        )
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
        """The clearance map: the placed footprints with their gap and nothing else, so a window may cross a lane the footprint will displace."""
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
        """Where each own pin's lanes may end, one entry per lane with a placed partner: the straight cells of the partner pin's own lanes (a lane attaches on no bend), else every attach cell the partner pin may still use."""
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
                    cells = lane_ends(
                        world, net, partner, 0 if cell_id == sink else 1, self.policy
                    )
                if cells is None:
                    cells = {xy for _, xy in world.open_ports(other, other_pin)}
                out.append((mine, sorted(cells)))
        return out

    @property
    def policy(self) -> Any:
        """The lane policy the world's router lays lanes with, or the project's own."""
        found = getattr(self.world.router, "policy", None)
        return found if found is not None else LanePolicy()


class EndfieldSearch(Search):
    """The regional construction, its jitter drawn from the raw seed over the cells in their declared order: bricks and entries (cells no net touches) first, then cells with a placed neighbour, neighbours being the two ends of a lane."""

    defaults = DEFAULTS
    proposer = EndfieldProposals

    def __init__(self, ctx: Any, settings: dict[str, Any] | None = None) -> None:
        super().__init__(ctx, settings)
        self.rng = random.Random(ctx.seed)
        declared = ctx.problem.netlist.cells
        if set(declared) == set(self.cells):
            self.cells = declared

    @staticmethod
    def neighbourhood(netlist: Any) -> dict[str, list[str]]:
        """The links: a lane's source and sink cells are neighbours, once per lane, so a pair two lanes join counts twice; nothing else on the net is."""
        out: dict[str, list[str]] = {c: [] for c in netlist.cells}
        for net in netlist.nets.values():
            for (source, _), (sink, _), _ in lane_facts(net):
                out[source].append(sink)
                out[sink].append(source)
        return out

    def priority(self, cell_id: str, placed: Any, jitter: dict[str, float]) -> tuple:
        n = sum(j in placed for j in self.neighbours[cell_id])
        fp = self.world.footprint_of(cell_id)
        unwired = not self.world.netlist.pins_of(cell_id)
        return (
            unwired,
            n > 0,
            self.pressure[cell_id] + n / (len(self.neighbours[cell_id]) or 1),
            n,
            fp.width * fp.height,
            jitter[cell_id],
        )


@register
class EndfieldRegional(Regional):
    id = "endfield.regional"
    search = EndfieldSearch
    params = (
        *(_param(k, v) for k, v in DEFAULTS.items()),
        Param(name="shrink_rounds", type="int", default=200),
    )


__all__ = ["DEFAULTS", "EndfieldProposals", "EndfieldRegional", "EndfieldSearch"]
