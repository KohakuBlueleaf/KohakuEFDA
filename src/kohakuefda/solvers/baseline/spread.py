"""First-complete lattice construction through the public framework builder."""

import logging
import random
import time

from kohakuefda.framework.context import Context
from kohakuefda.framework.control import Rejected

log = logging.getLogger(__name__)


class Spread:
    """Seeded flow-order retries; each machine placement includes its routing."""

    def __init__(self, context: Context, settings: dict) -> None:
        self.ctx = context
        self.settings = settings
        self.rng = random.Random(context.seed)
        self.reverse = settings["flow_order"] == "top-down"
        self.tried = 0
        self.order = []
        self.next_square = 0
        self.squares = []
        self.groups = {}
        for block in context.blocks.values():
            if block.group:
                self.groups.setdefault(block.group, []).append(block.id)

    def traversal(self, shuffle: bool) -> list[str]:
        blocks, links = self.ctx.blocks, self.ctx.links
        rank = dict.fromkeys(blocks, 0)
        for _ in blocks:
            changed = False
            for link in links:
                a, b = link.source, link.sink
                if a != b and rank[b] <= rank[a]:
                    rank[b] = rank[a] + 1
                    changed = True
            if not changed:
                break
        for group in self.groups.values():
            value = min(rank[i] for i in group)
            for i in group:
                rank[i] = value
        deepest = max(rank.values(), default=0)
        after = {i: [] for i in blocks}
        for link in links:
            a, b = (
                (link.sink, link.source) if self.reverse else (link.source, link.sink)
            )
            if a != b and b not in after[a]:
                after[a].append(b)

        def depth(i):
            return deepest - rank[i] if self.reverse else rank[i]

        jitter = (lambda i: self.rng.random()) if shuffle else (lambda i: 0.0)
        roots = sorted(blocks, key=lambda i: (depth(i), jitter(i), i))
        seen, out = set(), []
        for root in roots:
            stack = [root] if root not in seen else []
            while stack:
                i = stack.pop()
                if i in seen:
                    continue
                group = self.groups[blocks[i].group] if blocks[i].group else [i]
                for member in sorted(
                    group, key=lambda k: (blocks[k].kind not in ("depot", "zone"), k)
                ):
                    if member not in seen:
                        seen.add(member)
                        out.append(member)
                stack += sorted(
                    (k for k in after[i] if k not in seen),
                    key=lambda k: (-depth(k), jitter(k), k),
                )
        return out

    def lattice(self, gap: int) -> list[tuple[int, int]]:
        free = [
            b
            for b in self.ctx.blocks.values()
            if b.constraint not in ("slot", "edge") and not b.group
        ]
        pitch = (
            max((max(b.width, b.height) for b in free), default=1)
            + self.ctx.pylon_width
            + gap
        )
        x0, y0, x1, y1 = self.ctx.area
        cols, rows = max(1, (x1 - x0) // pitch), max(1, (y1 - y0) // pitch)
        return [
            (x0 + x * pitch, y0 + y * pitch)
            for y in range(rows)
            for x in (range(cols) if y % 2 == 0 else reversed(range(cols)))
        ]

    def turns(self, block_id: str) -> list[int]:
        anchors = dict(self.ctx.anchors)
        partners = [
            anchors[other][:2]
            for link in self.ctx.links
            for other in (
                [link.sink]
                if link.source == block_id
                else [link.source] if link.sink == block_id else []
            )
            if other != block_id and other in anchors
        ]
        if not partners or self.next_square >= len(self.squares):
            return [0, 90, 180, 270]
        x, y = self.squares[self.next_square]
        px, py = sum(a for a, _ in partners) / len(partners), sum(
            b for _, b in partners
        ) / len(partners)
        block = self.ctx.blocks[block_id]
        return sorted(
            (0, 90, 180, 270),
            key=lambda r: min(
                (
                    abs(x + dx - px) + abs(y + dy - py)
                    for dx, dy in block.ports[r // 90]
                ),
                default=0,
            ),
        )

    def constrained(self, block_id: str) -> tuple | None:
        block = self.ctx.blocks[block_id]
        anchors = dict(self.ctx.anchors)
        if block.constraint == "slot":
            return self.ctx.slot_anchors(block_id)
        if block.constraint == "edge":
            target = self.ctx.area[:2]
            for link in self.ctx.links:
                if link.source == block_id and link.sink in anchors:
                    target = anchors[link.sink][:2]
                    break
            return tuple(
                sorted(
                    self.ctx.border_anchors(),
                    key=lambda a: abs(a[0] - target[0]) + abs(a[1] - target[1]),
                )
            )
        if block.group and any(
            i in anchors and i != block_id for i in self.groups[block.group]
        ):
            return self.ctx.group_anchors(block_id)
        return None

    def stand(self, builder, block_id: str) -> bool:
        allowed = self.constrained(block_id)
        if allowed is not None:
            return any(builder.place(block_id, a).status == "placed" for a in allowed)
        start = self.next_square
        for step in range(len(self.squares)):
            index = (start + step) % len(self.squares)
            x, y = self.squares[index]
            for rotation in self.turns(block_id):
                if builder.place(block_id, (x, y, rotation)).status == "placed":
                    self.next_square = index + 1
                    return True
        return False

    def run(self) -> bool:
        ctx, cfg = self.ctx, self.settings
        builder = ctx.builder()
        gaps = list(range(cfg["spread_gap"], cfg["spread_widest"] + 1))
        first = self.reverse
        best = None
        started = time.monotonic()
        for attempt in range(cfg["spread_attempts"]):
            ctx.budget.charge("spread_attempts")
            gap = gaps[attempt % len(gaps)]
            self.reverse = first ^ bool((attempt // len(gaps)) % 2)
            builder.reset()
            self.squares, self.next_square = self.lattice(gap), 0
            self.order = self.traversal(attempt >= 2 * len(gaps))
            missed = []
            for block_id in self.order:
                if not self.stand(builder, block_id):
                    missed.append(block_id)
                ctx.frame("build")
            for block_id in list(missed):
                if self.stand(builder, block_id):
                    missed.remove(block_id)
            self.tried = attempt + 1
            view = ctx.view
            score = len(missed), len(view.unrouted), view.wire_cells
            if best is None or score < best[0]:
                if best is not None:
                    builder.release(best[1])
                best = score, builder.mark(), list(self.order)
            ctx.emit(
                "progress",
                {
                    "phase": "spread",
                    "attempt": self.tried,
                    "gap": gap,
                    "unplaced": len(missed),
                },
            )
            if not missed and not view.unrouted:
                try:
                    builder.finish()
                    break
                except Rejected:
                    continue
        else:
            builder.restore(best[1])
            self.order = best[2]
            ctx.diagnostic = builder.diagnostic()
            return False
        ctx.frame("build")
        log.info(
            "spread done",
            attempts=self.tried,
            seconds=round(time.monotonic() - started, 2),
            placed=len(ctx.view.anchors),
        )
        return True
