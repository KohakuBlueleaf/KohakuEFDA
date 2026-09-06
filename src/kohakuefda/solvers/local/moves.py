"""Shared coupled construction repair and complete-layout mutation operators."""

from kohakuefda.framework.control import Rejected
from kohakuefda.model.geometry import ROTATIONS
from kohakuefda.model.solver import Action
from kohakuefda.solvers.local.compact import CompactionMoves
from kohakuefda.solvers.local.repack import RepackMoves
from kohakuefda.solvers.regional import DEFAULTS as REGIONAL_DEFAULTS
from kohakuefda.solvers.regional.search import Search


class ConstructionSearch(Search):
    def insert(self, block_id, anchors):
        if not self.settings["insertion_lookahead"]:
            return super().insert(block_id, anchors)
        before = self.builder.mark()
        best = None
        best_cost = float("inf")
        chosen = None
        remaining = None
        try:
            for anchor in anchors:
                if remaining is not None:
                    remaining -= 1
                    if remaining < 0:
                        break
                result = self.builder.place(block_id, anchor)
                if result.status != "placed":
                    continue
                if remaining is None:
                    remaining = self.settings["insertion_lookahead"]
                cost = self.context.view.wire_cells
                if cost < best_cost:
                    if best is not None:
                        self.builder.release(best)
                    best = self.builder.mark()
                    best_cost, chosen = cost, anchor
                self.builder.restore(before)
            if best is None:
                return False
            self.builder.restore(best)
            self.proposals.occupy(block_id, chosen)
            return True
        finally:
            self.builder.release(before)
            if best is not None:
                self.builder.release(best)


class ConstructionMoves:
    """Reuse regional insertion/region operators without its best-prefix search policy."""

    def __init__(self, context, settings) -> None:
        self.context = context
        self.repair = ConstructionSearch(
            context,
            {
                **REGIONAL_DEFAULTS,
                "candidates": settings["candidates"],
                "gap": settings["gap"],
                "insertion_lookahead": settings["insertion_lookahead"],
            },
        )
        self.repair.rng = context.rng("local.proposals")
        self.settings = settings

    def prepare(self, step):
        if (
            self.settings["local_repair_every"]
            and step % self.settings["local_repair_every"]
        ):
            placed = dict(self.context.anchors)
            free = [
                i
                for i in placed
                if self.context.blocks[i].constraint == "free"
                and not self.context.blocks[i].group
            ]
            if not free:
                return "local"
            root = self.repair.rng.choice(free)
            x, y, _ = placed[root]
            near = sorted(
                free, key=lambda i: abs(placed[i][0] - x) + abs(placed[i][1] - y)
            )
            size = self.repair.rng.randint(1, self.settings["local_repair_size"])
            result = self.repair.builder.withdraw(tuple(near[:size]))
            if result.status != "removed":
                raise Rejected(result.message, result.status)
            return "local"
        result = self.repair.builder.withdraw(self.region(step))
        if result.status != "removed":
            raise Rejected(result.message, result.status)
        return "regional"

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
