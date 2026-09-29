"""The move sets: construction repair through the regional operators, and complete-layout mutations."""

import random
from collections.abc import Callable
from typing import Any

from kohakulayout.ir import Refusal
from kohakulayout.ir.geometry import footprint_cells
from kohakulayout.solvers.local.compact import CompactionMoves, relocate, standing_cells
from kohakulayout.solvers.local.repack import RepackMoves
from kohakulayout.solvers.local.selection import OperatorSelection, reward
from kohakulayout.solvers.regional.candidates import is_free
from kohakulayout.solvers.regional.search import Search

Move = Callable[[Any], Any]
Proposal = tuple[str, Move | None]
Anchors = dict[str, tuple[int, int, int]]
SCREENED = frozenset({"shift", "rotate", "swap", "cluster"})
STATISTICS_EVERY = 256


class ConstructionMoves:
    """Reuse the regional insertion and region operators without its best-prefix policy."""

    def __init__(
        self, ctx: Any, settings: dict[str, Any], search: type = Search
    ) -> None:
        self.ctx = ctx
        self.settings = settings
        self.repair = search(
            ctx, {k: settings[k] for k in search.defaults if k in settings}
        )
        self.repair.rng = random.Random(ctx.rng.randrange(2**32))

    def region(self, step: int) -> list[str]:
        world = self.ctx.world
        self.repair.best_missing = [
            c for c in world.netlist.cells if c not in world.placements
        ]
        return sorted(self.repair.region(step))

    def local_region(self) -> list[str]:
        world = self.ctx.world
        placed = world.placements
        free = sorted(c for c in placed if is_free(world.netlist.cells[c]))
        if not free:
            return []

        root = self.repair.rng.choice(free)
        rx, ry = placed[root].x, placed[root].y
        near = sorted(
            free, key=lambda c: (abs(placed[c].x - rx) + abs(placed[c].y - ry), c)
        )
        return near[: self.repair.rng.randint(1, self.settings["local_repair_size"])]

    def step(self, step: int) -> tuple[str, Move]:
        """The operator name and the attempt body: withdraw a region, then refill."""
        every = self.settings["local_repair_every"]
        local = bool(every and step % every)
        removed = self.local_region() if local else self.region(step)
        if not step or not self.ctx.world.placements:
            removed = []

        def body(builder: Any) -> None:
            for cell_id in removed:
                if cell_id in builder.placements:
                    builder.withdraw(cell_id)
            for cell_id in self.repair.pressure:
                missing = cell_id not in builder.placements and step
                self.repair.pressure[cell_id] = (
                    self.settings["repair_pressure"] if missing else 0.0
                )
            self.repair.construct(builder, step)

        return ("local" if local else "regional"), body


class LayoutMoves:
    """Local, route, compaction, repack and reseat moves over a complete layout, the
    ordinary operators drawn uniformly or by their measured reward."""

    def __init__(
        self, ctx: Any, settings: dict[str, Any], search: type = Search
    ) -> None:
        self.ctx = ctx
        self.world = ctx.world
        self.settings = settings
        self.rng = random.Random(ctx.rng.randrange(2**32))
        self.reseated = search.reseated
        self.free = tuple(
            sorted(c for c, cell in self.world.netlist.cells.items() if is_free(cell))
        )
        related = search.neighbourhood(self.world.netlist)
        self.neighbours: dict[str, set[str]] = {
            c: {b for b in related.get(c, ()) if b in self.free and b != c}
            for c in self.free
        }

        self.compaction = CompactionMoves(self.world, settings, self.rng)
        self.repacking = (
            RepackMoves(self.world, settings, self.rng, search.proposer)
            if settings["repack_every"]
            else None
        )

        self.operators: tuple[Callable[[], Proposal], ...] = (
            self.shift,
            self.rotate,
            self.swap,
            self.cluster,
            self.reroute,
            self.reroute_all,
        )
        if settings["compaction_moves"]:
            compaction = (self.cut, self.pull, self.press)
            self.operators = (*self.operators, *compaction, *compaction)

        self.by_name = {op.__name__: op for op in self.operators}
        self.selection = (
            OperatorSelection(
                tuple(self.by_name),
                self.rng,
                decay=settings["operator_decay"],
                exploration=settings["operator_exploration"],
            )
            if settings["adaptive_moves"]
            else None
        )
        self.calls = 0
        self.observations = 0

    def propose(self) -> Proposal:
        every = self.settings["reseat_every"]
        if every and (self.calls + 1) % every == 0:
            self.calls += 1
            return self.reseat(paired=bool(self.calls % (2 * every)))

        self.calls += 1
        if (
            self.repacking is not None
            and self.calls % self.settings["repack_every"] == 0
        ):
            selected = self.repacking.choose()
            if not selected:
                return "repack", None
            return "repack", lambda b, s=selected: self.repacking.execute(b, s)

        if self.selection is None:
            return self.rng.choice(self.operators)()
        return self.by_name[self.selection.choose()]()

    def feedback(
        self, name: str, delta: float | None, accepted: bool, work: int
    ) -> None:
        """Credit an ordinary operator with its proposal's outcome per charged work."""
        if self.selection is None or name not in self.selection.stats:
            return

        self.selection.observe(name, reward(delta, accepted), work)
        self.observations += 1
        if self.observations % STATISTICS_EVERY == 0:
            self.ctx.log("operator selection", operators=self.selection.summary())

    def delta(self) -> tuple[int, int]:
        distance = self.rng.randint(1, self.settings["move_radius"])
        return self.rng.choice(
            ((distance, 0), (-distance, 0), (0, distance), (0, -distance))
        )

    def _relocation(self, name: str, moves: Anchors | None) -> Proposal:
        if not moves:
            return name, None
        if (
            self.settings.get("screen_moves")
            and name in SCREENED
            and self.estimate(moves) > 0
        ):
            return name, None

        batch = self.settings.get("batch_moves", False)
        return name, lambda b, m=moves: relocate(b, m, batch=batch)

    def estimate(self, moves: Anchors) -> int:
        """How much longer the touched nets' half perimeters get; positive means the move is dropped unheard."""
        placed = self.world.placements
        before = after = 0
        for net in self.world.netlist.nets.values():
            cells = [r.cell for r in net.pins()]
            if not any(c in moves for c in cells):
                continue

            old = [(placed[c].x, placed[c].y) for c in cells if c in placed]
            new = [
                moves[c][:2] if c in moves else (placed[c].x, placed[c].y)
                for c in cells
                if c in moves or c in placed
            ]
            before += half_perimeter(old)
            after += half_perimeter(new)
        return after - before

    def shift(self) -> Proposal:
        if not self.free:
            return "shift", None

        cell_id = self.rng.choice(self.free)
        p = self.world.placements[cell_id]
        dx, dy = self.delta()
        return self._relocation("shift", {cell_id: (p.x + dx, p.y + dy, p.rot)})

    def rotate(self) -> Proposal:
        if not self.free:
            return "rotate", None

        cell_id = self.rng.choice(self.free)
        p = self.world.placements[cell_id]
        options = [r for r in self.world.footprint_of(cell_id).rotations if r != p.rot]
        if not options:
            return "rotate", None
        return self._relocation(
            "rotate", {cell_id: (p.x, p.y, self.rng.choice(options))}
        )

    def swap(self) -> Proposal:
        if len(self.free) < 2:
            return "swap", None

        a, b = self.rng.sample(self.free, 2)
        pa, pb = self.world.placements[a], self.world.placements[b]
        return self._relocation(
            "swap", {a: (pb.x, pb.y, pa.rot), b: (pa.x, pa.y, pb.rot)}
        )

    def cluster(self) -> Proposal:
        if not self.free:
            return "cluster", None

        selected = [self.rng.choice(self.free)]
        for _ in range(self.settings["cluster_size"] - 1):
            frontier = sorted(
                {j for i in selected for j in self.neighbours[i]} - set(selected)
            )
            if not frontier:
                break
            selected.append(self.rng.choice(frontier))

        dx, dy = self.delta()
        placed = self.world.placements
        return self._relocation(
            "cluster",
            {c: (placed[c].x + dx, placed[c].y + dy, placed[c].rot) for c in selected},
        )

    def reroute(self) -> Proposal:
        nets = sorted(self.world.netlist.nets)
        if not nets:
            return "reroute", None
        net_id = self.rng.choice(nets)

        def body(builder: Any) -> Refusal | None:
            builder.unroute(net_id)
            return builder.route(net_id)

        return "reroute", body

    def reroute_all(self) -> Proposal:
        """Every net unrouted, then routed again in a random order."""
        nets = sorted(self.world.netlist.nets)
        if len(nets) < 2:
            return "reroute_all", None
        self.rng.shuffle(nets)

        def body(builder: Any) -> Refusal | None:
            for net_id in nets:
                builder.unroute(net_id)
            for net_id in nets:
                refusal = builder.route(net_id)
                if refusal is not None:
                    return refusal
            return None

        return "reroute_all", body

    def cut(self) -> Proposal:
        return self._relocation("cut", self.compaction.cut())

    def pull(self) -> Proposal:
        return self._relocation("pull", self.compaction.pull())

    def press(self) -> Proposal:
        return self._relocation("press", self.compaction.press())

    def reseat(self, paired: bool) -> Proposal:
        """A cell of a ``reseated`` constraint kind to another of its own anchors, alone
        or with one free partner; the cheapest ``reseat_candidates`` by extent plus wire
        estimate are sampled."""
        world = self.world
        placed = world.placements
        seated = sorted(
            c for c in placed if world.netlist.cells[c].constraint.kind in self.reseated
        )
        if not seated:
            return "reseat", None

        cell_id = self.rng.choice(seated)
        members = {cell_id}
        if paired:
            partners = sorted(self.partners(cell_id).intersection(self.free))
            if not partners:
                return "reseat", None
            members.add(self.rng.choice(partners))

        fixed = {
            xy
            for cell, cells in standing_cells(world).items()
            if cell not in members
            for xy in cells
        }
        home = placed[cell_id]
        candidates = []
        for anchor in world.anchors(cell_id):
            dx, dy = anchor.x - home.x, anchor.y - home.y
            if anchor.rot != home.rot or dx == dy == 0:
                continue

            moves = {
                c: (placed[c].x + dx, placed[c].y + dy, placed[c].rot) for c in members
            }
            taken = self.landed(moves, fixed)
            if taken is not None:
                cost = extent(taken) + self.estimate(moves)
                candidates.append((cost, anchor.x, anchor.y, moves))

        candidates.sort(key=lambda candidate: candidate[:3])
        count = self.settings["reseat_candidates"]
        moves = (
            self.rng.choice(candidates[:count])[-1]
            if candidates and count > 0
            else None
        )
        return self._relocation("reseat", moves)

    def partners(self, cell_id: str) -> set[str]:
        """The placed cells sharing a net with the cell."""
        out: set[str] = set()
        for net in self.world.netlist.nets.values():
            ids = {ref.cell for ref in net.pins()}
            if cell_id in ids:
                out.update(ids)
        out.discard(cell_id)
        return out.intersection(self.world.placements)

    def landed(self, moves: Anchors, fixed: set) -> set | None:
        """Every cell the moved footprints and the fixed cells take, or None when a footprint overlaps or leaves the build area."""
        taken = set(fixed)
        for cell_id, (x, y, rot) in moves.items():
            fp = self.world.footprint_of(cell_id)
            cells = set(footprint_cells(x, y, fp.width, fp.height, rot))
            if cells & taken or any(not self.world.in_build(xy) for xy in cells):
                return None
            taken.update(cells)
        return taken


def half_perimeter(points: list[tuple[int, int]]) -> int:
    if len(points) < 2:
        return 0
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    return max(xs) - min(xs) + max(ys) - min(ys)


def extent(cells: set) -> int:
    xs = [x for x, _ in cells]
    ys = [y for _, y in cells]
    return (max(xs) - min(xs) + 1) * (max(ys) - min(ys) + 1)


MOVES: dict[str, str] = {
    name: name
    for name in (
        "shift",
        "rotate",
        "swap",
        "cluster",
        "reroute",
        "reroute_all",
        "cut",
        "pull",
        "press",
        "repack",
        "reseat",
    )
}

__all__ = ["MOVES", "ConstructionMoves", "LayoutMoves", "Move", "Proposal"]
