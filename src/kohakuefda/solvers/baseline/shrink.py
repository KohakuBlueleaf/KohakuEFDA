"""Greedy compaction policy over transactional framework actions."""

from kohakuefda.framework.context import Context
from kohakuefda.model.solver import Action, Scope

PINNED = ("slot", "edge")
SIDES = ((0, -1), (1, -1), (0, 1), (1, 1))


class Shrink:
    def __init__(self, context: Context, order: tuple[str, ...], rounds: int) -> None:
        self.ctx, self.order, self.rounds = context, order, rounds

    def take(self, action: Action) -> bool:
        ctx = self.ctx
        candidate = ctx.attempt(action).candidate
        if candidate is None:
            return False
        if ctx.objective.key(candidate.snapshot.assessment) < ctx.objective.key(
            ctx.current.assessment
        ):
            ctx.accept(candidate)
            return True
        ctx.discard(candidate)
        return False

    def rebuild(self, anchors: dict) -> bool:
        return self.take(
            Action(
                "rebuild",
                tuple(anchors.items()),
                self.order,
                scope=Scope(frozenset(anchors)),
            )
        )

    def carve(self) -> bool:
        view = self.ctx.view
        standing = {c for _, cells in view.footprints for c in cells}
        for axis in (0, 1):
            lines = set(range(view.bbox[axis], view.bbox[axis + 2])) - {
                c[axis] for c in standing
            }
            for line in sorted(lines, reverse=True):
                anchors = {}
                for i, anchor in view.anchors:
                    spot = list(anchor)
                    if (
                        self.ctx.blocks[i].constraint not in PINNED
                        and spot[axis] > line
                    ):
                        spot[axis] -= 1
                    anchors[i] = tuple(spot)
                if self.rebuild(anchors):
                    return True
        return False

    def press(self, axis: int, step: int) -> bool:
        ctx, view = self.ctx, self.ctx.view
        placed, cells_of = dict(view.anchors), dict(view.footprints)
        order = sorted(placed, key=lambda i: placed[i][axis] * -step)
        taken = {
            c for i in order if ctx.blocks[i].constraint in PINNED for c in cells_of[i]
        }
        anchors = {}
        x0, y0, x1, y1 = view.area
        for i in order:
            spot = list(placed[i])
            if ctx.blocks[i].constraint not in PINNED:
                cells = cells_of[i]
                while True:
                    moved = [
                        (x + step, y) if axis == 0 else (x, y + step) for x, y in cells
                    ]
                    if any(
                        not (x0 <= x < x1 and y0 <= y < y1) or (x, y) in taken
                        for x, y in moved
                    ):
                        break
                    spot[axis] += step
                    cells = moved
                taken.update(cells)
            anchors[i] = tuple(spot)
        return self.rebuild(anchors)

    def nudge(self) -> bool:
        ctx = self.ctx
        placed = dict(ctx.view.anchors)
        for i, (x, y, rotation) in placed.items():
            if ctx.blocks[i].constraint in PINNED:
                continue
            partners = [
                placed[other][:2]
                for link in ctx.links
                for other in (
                    [link.sink]
                    if link.source == i
                    else [link.source] if link.sink == i else []
                )
                if other in placed and other != i
            ]
            steps = sorted(
                ((1, 0), (-1, 0), (0, 1), (0, -1)),
                key=lambda s: sum(
                    abs(x + s[0] - px) + abs(y + s[1] - py) for px, py in partners
                ),
            )
            for dx, dy in steps:
                if self.take(Action("relocate", ((i, (x + dx, y + dy, rotation)),))):
                    return True
        return False

    def run(self) -> None:
        for step in range(self.rounds):
            self.ctx.budget.check()
            if (
                not self.carve()
                and not any(self.press(a, s) for a, s in SIDES)
                and not self.nudge()
            ):
                break
            self.ctx.frame("improve", step=step + 1, of=self.rounds)
