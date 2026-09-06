"""Shared coupled construction repair and complete-layout mutation operators."""

from kohakuefda.model.geometry import ROTATIONS
from kohakuefda.model.solver import Action
from kohakuefda.solvers.local.compact import CompactionMoves
from kohakuefda.solvers.local.repack import RepackMoves
from kohakuefda.solvers.regional import DEFAULTS as REGIONAL_DEFAULTS
from kohakuefda.solvers.regional.search import Search


class ConstructionMoves:
    """Reuse regional insertion/region operators without its best-prefix search policy."""

    def __init__(self, context, settings) -> None:
        self.context = context
        self.repair = Search(
            context,
            {
                **REGIONAL_DEFAULTS,
                "candidates": settings["candidates"],
                "gap": settings["gap"],
            },
        )
        self.repair.rng = context.rng("local.proposals")

    def region(self, step: int) -> tuple[str, ...]:
        placed = dict(self.context.anchors)
        self.repair.best_missing = [i for i in self.context.blocks if i not in placed]
        return tuple(sorted(self.repair.region(step)))

    def fill(self, step: int) -> None:
        placed = dict(self.context.anchors)
        for block_id in self.repair.pressure:
            self.repair.pressure[block_id] = (
                self.repair.settings["repair_pressure"]
                if block_id not in placed and step
                else 0.0
            )
        self.repair.construct(step)


class LayoutMoves:
    """Sample a shared mixture of local, route and coordinated compaction moves."""

    def __init__(self, context, settings) -> None:
        self.context = context
        self.settings = settings
        self.rng = context.rng("local.proposals")
        self.free = tuple(
            i
            for i, block in context.blocks.items()
            if block.constraint == "free" and not block.group
        )
        self.neighbors = {i: set() for i in self.free}
        for link in context.links:
            if link.source in self.neighbors and link.sink in self.neighbors:
                self.neighbors[link.source].add(link.sink)
                self.neighbors[link.sink].add(link.source)
        self.compaction = CompactionMoves(context, settings, self.rng)
        self.operators = (
            self.shift,
            self.rotate,
            self.swap,
            self.cluster,
            self.reroute,
        )
        if settings["compaction_moves"]:
            self.operators = (
                *self.operators,
                self.compaction.cut,
                self.compaction.pull,
                self.compaction.pull,
                self.compaction.cut,
            )

        self.repacking = (
            RepackMoves(context, settings, self.rng)
            if settings["repack_every"]
            else None
        )
        self.calls = 0

    def close(self) -> None:
        if self.repacking is not None:
            self.repacking.close()

    def propose(self) -> tuple[str, Action | None]:
        self.calls += 1
        if (
            self.repacking is not None
            and self.calls % self.settings["repack_every"] == 0
        ):
            return "repack", self.repacking.repack()
        operator = self.rng.choice(self.operators)
        return operator.__name__, operator()

    def delta(self) -> tuple[int, int]:
        distance = self.rng.randint(1, self.settings["move_radius"])
        return self.rng.choice(
            ((distance, 0), (-distance, 0), (0, distance), (0, -distance))
        )

    def shift(self) -> Action | None:
        if not self.free:
            return None
        block_id = self.rng.choice(self.free)
        x, y, rotation = dict(self.context.anchors)[block_id]
        dx, dy = self.delta()
        return Action("relocate", ((block_id, (x + dx, y + dy, rotation)),))

    def rotate(self) -> Action | None:
        if not self.free:
            return None
        block_id = self.rng.choice(self.free)
        x, y, rotation = dict(self.context.anchors)[block_id]
        turned = self.rng.choice([r for r in ROTATIONS if r != rotation])
        return Action("relocate", ((block_id, (x, y, turned)),))

    def swap(self) -> Action | None:
        if len(self.free) < 2:
            return None
        a, b = self.rng.sample(self.free, 2)
        placed = dict(self.context.anchors)
        ax, ay, ar = placed[a]
        bx, by, br = placed[b]
        return Action("relocate", ((a, (bx, by, ar)), (b, (ax, ay, br))))

    def cluster(self) -> Action | None:
        if not self.free:
            return None
        root = self.rng.choice(self.free)
        selected = [root]
        for _ in range(self.settings["cluster_size"] - 1):
            frontier = sorted(
                {j for i in selected for j in self.neighbors[i]} - set(selected)
            )
            if not frontier:
                break
            selected.append(self.rng.choice(frontier))
        placed = dict(self.context.anchors)
        dx, dy = self.delta()
        return Action(
            "relocate",
            tuple(
                (i, (placed[i][0] + dx, placed[i][1] + dy, placed[i][2]))
                for i in selected
            ),
        )

    def reroute(self) -> Action | None:
        if not self.context.links:
            return None
        return Action("reroute", routes=(self.rng.choice(self.context.links).id,))
