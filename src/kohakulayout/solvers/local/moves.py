"""The move sets: construction repair through the regional operators, and complete-layout mutations."""

import random
from collections.abc import Callable
from typing import Any

from kohakulayout.ir import Refusal
from kohakulayout.solvers.local.compact import CompactionMoves, relocate
from kohakulayout.solvers.local.repack import RepackMoves
from kohakulayout.solvers.regional.candidates import is_free
from kohakulayout.solvers.regional.search import DEFAULTS as REGIONAL_DEFAULTS
from kohakulayout.solvers.regional.search import Search

Move = Callable[[Any], Any]


class ConstructionMoves:
    """Reuse the regional insertion and region operators without its best-prefix policy."""

    def __init__(self, ctx: Any, settings: dict[str, Any]) -> None:
        self.ctx = ctx
        self.settings = settings
        self.repair = Search(
            ctx,
            {
                **REGIONAL_DEFAULTS,
                "candidates": settings["candidates"],
                "gap": settings["gap"],
            },
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
        removed = self.local_region() if every and step % every else self.region(step)
        name = "local" if every and step % every else "regional"
        if not step or not self.ctx.world.placements:
            removed = []

        def body(builder: Any) -> None:
            for cell_id in removed:
                if cell_id in builder.placements:
                    builder.withdraw(cell_id)
            for cell_id in self.repair.pressure:
                self.repair.pressure[cell_id] = (
                    self.settings["repair_pressure"]
                    if cell_id not in builder.placements and step
                    else 0.0
                )
            self.repair.construct(builder, step)

        return name, body


class LayoutMoves:
    """A shared mixture of local, route and compaction moves over a complete layout."""

    def __init__(self, ctx: Any, settings: dict[str, Any]) -> None:
        self.ctx = ctx
        self.world = ctx.world
        self.settings = settings
        self.rng = random.Random(ctx.rng.randrange(2**32))
        self.free = tuple(
            sorted(c for c, cell in self.world.netlist.cells.items() if is_free(cell))
        )
        self.neighbours: dict[str, set[str]] = {c: set() for c in self.free}
        for net in self.world.netlist.nets.values():
            cells = [r.cell for r in net.pins()]
            for a in cells:
                if a in self.neighbours:
                    self.neighbours[a].update(
                        b for b in cells if b != a and b in self.neighbours
                    )
        self.compaction = CompactionMoves(self.world, settings, self.rng)
        self.repacking = (
            RepackMoves(self.world, settings, self.rng)
            if settings["repack_every"]
            else None
        )
        self.operators: tuple[Callable[[], tuple[str, Move | None]], ...] = (
            self.shift,
            self.rotate,
            self.swap,
            self.cluster,
            self.reroute,
        )
        if settings["compaction_moves"]:
            self.operators = (*self.operators, self.cut, self.pull, self.pull, self.cut)
        self.calls = 0

    def propose(self) -> tuple[str, Move | None]:
        self.calls += 1
        if (
            self.repacking is not None
            and self.calls % self.settings["repack_every"] == 0
        ):
            selected = self.repacking.choose()
            return "repack", (
                (lambda b, s=selected: self.repacking.execute(b, s))
                if selected
                else None
            )
        return self.rng.choice(self.operators)()

    def delta(self) -> tuple[int, int]:
        distance = self.rng.randint(1, self.settings["move_radius"])
        return self.rng.choice(
            ((distance, 0), (-distance, 0), (0, distance), (0, -distance))
        )

    def _relocation(
        self, name: str, moves: dict[str, tuple[int, int, int]] | None
    ) -> tuple[str, Move | None]:
        if not moves:
            return name, None
        return name, lambda b, m=moves: relocate(b, m)

    def shift(self) -> tuple[str, Move | None]:
        if not self.free:
            return "shift", None
        cell_id = self.rng.choice(self.free)
        p = self.world.placements[cell_id]
        dx, dy = self.delta()
        return self._relocation("shift", {cell_id: (p.x + dx, p.y + dy, p.rot)})

    def rotate(self) -> tuple[str, Move | None]:
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

    def swap(self) -> tuple[str, Move | None]:
        if len(self.free) < 2:
            return "swap", None
        a, b = self.rng.sample(self.free, 2)
        pa, pb = self.world.placements[a], self.world.placements[b]
        return self._relocation(
            "swap", {a: (pb.x, pb.y, pa.rot), b: (pa.x, pa.y, pb.rot)}
        )

    def cluster(self) -> tuple[str, Move | None]:
        if not self.free:
            return "cluster", None
        root = self.rng.choice(self.free)
        selected = [root]
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

    def reroute(self) -> tuple[str, Move | None]:
        nets = sorted(self.world.netlist.nets)
        if not nets:
            return "reroute", None
        net_id = self.rng.choice(nets)

        def body(builder: Any) -> Refusal | None:
            builder.unroute(net_id)
            return builder.route(net_id)

        return "reroute", body

    def cut(self) -> tuple[str, Move | None]:
        return self._relocation("cut", self.compaction.cut())

    def pull(self) -> tuple[str, Move | None]:
        return self._relocation("pull", self.compaction.pull())


MOVES: dict[str, str] = {
    name: name
    for name in (
        "shift",
        "rotate",
        "swap",
        "cluster",
        "reroute",
        "cut",
        "pull",
        "repack",
    )
}

__all__ = ["MOVES", "ConstructionMoves", "LayoutMoves", "Move"]
