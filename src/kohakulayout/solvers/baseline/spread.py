"""First-complete lattice construction: cells in flow order on a lattice of squares, retried with wider gaps."""

import random
from typing import Any

from kohakulayout.ir.geometry import rotate_size
from kohakulayout.physics.protocol import Anchor
from kohakulayout.solvers.regional.candidates import Proposals, is_free
from kohakulayout.solvers.regional.search import clear, neighbours_of


class Spread:
    """Seeded flow-order retries; each placement routes what it completes."""

    def __init__(self, ctx: Any, settings: dict[str, Any]) -> None:
        self.ctx = ctx
        self.world = ctx.world
        self.settings = settings
        self.rng = random.Random(ctx.rng.randrange(2**32))
        self.reverse = settings["flow_order"] == "top-down"
        self.neighbours = neighbours_of(self.world.netlist)
        self.proposals = Proposals(self.world, {"candidates": 32})
        self.squares: list[tuple[int, int]] = []
        self.next_square = 0
        self.order: list[str] = []
        self.tried = 0

    def traversal(self, shuffle: bool) -> list[str]:
        """Producers before consumers by rank, groups kept together, jittered when asked."""
        netlist = self.world.netlist
        order, _ = netlist.flow_order()
        rank = {c: i for i, c in enumerate(order)}
        for group in netlist.groups.values():
            value = min(rank[m] for m in group.members)
            for m in group.members:
                rank[m] = value
        jitter = (lambda c: self.rng.random()) if shuffle else (lambda c: 0.0)
        deepest = max(rank.values(), default=0)
        depth = (lambda c: deepest - rank[c]) if self.reverse else (lambda c: rank[c])
        out: list[str] = []
        seen: set[str] = set()
        for cell_id in sorted(netlist.cells, key=lambda c: (depth(c), jitter(c), c)):
            cell = netlist.cells[cell_id]
            members = (
                list(netlist.groups[cell.group].members) if cell.group else [cell_id]
            )
            for member in members:
                if member not in seen:
                    seen.add(member)
                    out.append(member)
        return out

    def lattice(self, gap: int) -> list[tuple[int, int]]:
        world = self.world
        free = [
            world.footprint_of(c)
            for c, cell in world.netlist.cells.items()
            if is_free(cell)
        ]
        pitch = max((max(fp.width, fp.height) for fp in free), default=1) + gap
        width, height = world.fabric.width, world.fabric.height
        cols, rows = max(1, width // pitch), max(1, height // pitch)
        return [
            (x * pitch, y * pitch)
            for y in range(rows)
            for x in (range(cols) if y % 2 == 0 else reversed(range(cols)))
        ]

    def turns(self, cell_id: str, x: int, y: int) -> list[int]:
        """Rotations facing the placed partners first."""
        fp = self.world.footprint_of(cell_id)
        placed = self.world.placements
        partners = [
            (placed[o].x, placed[o].y) for o in self.neighbours[cell_id] if o in placed
        ]
        if not partners:
            return list(fp.rotations)
        px = sum(a for a, _ in partners) / len(partners)
        py = sum(b for _, b in partners) / len(partners)

        def distance(rot: int) -> float:
            offsets = self.proposals.offsets(cell_id, rot).values()
            return min(
                (abs(x + ox - px) + abs(y + oy - py) for ox, oy in offsets), default=0.0
            )

        return sorted(fp.rotations, key=distance)

    def constrained(self, cell_id: str) -> list[Anchor] | None:
        """Pack anchors for a pinned cell, sorted toward its placed partner; group windows for grouped cells."""
        world = self.world
        cell = world.netlist.cells[cell_id]
        placed = world.placements
        if cell.constraint.kind != "free":
            target = (0, 0)
            for other in self.neighbours[cell_id]:
                if other in placed:
                    target = (placed[other].x, placed[other].y)
                    break
            return sorted(
                world.anchors(cell_id),
                key=lambda a: (
                    abs(a.x - target[0]) + abs(a.y - target[1]),
                    a.y,
                    a.x,
                    a.rot,
                ),
            )
        if cell.group is not None:
            members = [
                m
                for m in world.netlist.groups[cell.group].members
                if m in placed and m != cell_id
            ]
            if members:
                return self.proposals.group_window(cell_id, members)
        return None

    def stand(self, builder: Any, cell_id: str) -> bool:
        allowed = self.constrained(cell_id)
        if allowed is not None:
            return any(
                builder.admits(cell_id, a.x, a.y, a.rot)
                and builder.place(cell_id, a) is None
                for a in allowed
            )
        fp = self.world.footprint_of(cell_id)
        start = self.next_square
        for step in range(len(self.squares)):
            index = (start + step) % len(self.squares)
            x, y = self.squares[index]
            for rot in self.turns(cell_id, x, y):
                w, h = rotate_size(fp.width, fp.height, rot)
                if x + w > self.world.fabric.width or y + h > self.world.fabric.height:
                    continue
                if (
                    builder.admits(cell_id, x, y, rot)
                    and builder.place(cell_id, Anchor(x=x, y=y, rot=rot)) is None
                ):
                    self.next_square = index + 1
                    return True
        return False

    def attempt(self, builder: Any, attempt: int, gaps: list[int]) -> list[str]:
        clear(builder)
        self.squares, self.next_square = self.lattice(gaps[attempt % len(gaps)]), 0
        self.order = self.traversal(attempt >= 2 * len(gaps))
        missed = [c for c in self.order if not self.stand(builder, c)]
        return [c for c in missed if not self.stand(builder, c)]

    def run(self) -> bool:
        ctx, cfg = self.ctx, self.settings
        gaps = list(range(cfg["spread_gap"], cfg["spread_widest"] + 1))
        first = self.reverse
        best: tuple[tuple[int, int, int], Any] | None = None
        for attempt in range(cfg["spread_attempts"]):
            self.reverse = first ^ bool((attempt // len(gaps)) % 2)
            missed: list[str] = []
            ctx.attempt(
                lambda b, a=attempt, m=missed: m.extend(self.attempt(b, a, gaps)),
                label="spread",
            )
            self.tried = attempt + 1
            unrouted = len(ctx.world.unrouted())
            score = (
                len(missed),
                unrouted,
                ctx.world.freeze().attrs.get("wire_cells", 0),
            )
            if best is None or score < best[0]:
                best = (score, ctx.snapshot())
            ctx.frame("spread")
            if not missed and not unrouted:
                ctx.consider()
                return True
        if best is not None:
            ctx.restore(best[1])
        return False


__all__ = ["Spread"]
