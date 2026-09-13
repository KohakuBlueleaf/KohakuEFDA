"""Regional construction: seeded frontier insertion, the best routed prefix retained, missing cells' neighbourhoods rebuilt."""

import random
from typing import Any

from kohakulayout.ir import Refusal
from kohakulayout.solvers.regional.candidates import Proposals, is_free

DEFAULTS: dict[str, Any] = {
    "attempts": 128,
    "candidates": 150,
    "gap": 2,
    "gap_cycle": 2,
    "refill_rounds": 1,
    "restart_cycle": 4,
    "repair_threshold": 0.85,
    "radius": 7,
    "radius_cycle": 14,
    "neighbor_cycle": 3,
    "expand_cycle": 5,
    "pressure_decay": 0.7,
    "failure_pressure": 0.5,
    "repair_pressure": 10.0,
    "replace_equal": 0.5,
    "jitter": 3.0,
    "closed_cost": 10000,
    "origin_weight": 0.2,
    "corner_weight": 0.015,
    "extent_weight": 1.0,
    "lookahead": 3,
    "insert_failures": 8,
}


def neighbours_of(netlist: Any) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {c: [] for c in netlist.cells}
    for net in netlist.nets.values():
        cells = [r.cell for r in net.pins()]
        for a in cells:
            for b in cells:
                if a != b and b not in out[a]:
                    out[a].append(b)
    return out


def clear(builder: Any) -> None:
    for cell_id in list(builder.placements):
        builder.withdraw(cell_id)


class Search:
    """The regional constructor over a context; ``run`` reaches a complete state or reports what is missing.

    A project's own construction subclasses this: ``defaults`` carries its settings,
    ``proposer`` its anchor ranking, ``neighbourhood`` which cells count as neighbours,
    and ``priority`` its insertion order.
    """

    defaults: dict[str, Any] = DEFAULTS
    proposer: type = Proposals

    def __init__(self, ctx: Any, settings: dict[str, Any] | None = None) -> None:
        self.ctx = ctx
        self.settings = {**self.defaults, **(settings or {})}
        self.world = ctx.world
        self.cells = self.world.netlist.cells
        self.rng = random.Random(ctx.rng.randrange(2**32))
        self.proposals = self.proposer(self.world, self.settings)
        self.neighbours = self.neighbourhood(self.world.netlist)
        self.pressure: dict[str, float] = dict.fromkeys(self.cells, 0.0)
        self.best_count = 0
        self.best_token: Any = None
        self.best_missing: list[str] = []
        self.empty = ctx.snapshot() if not self.world.placements else None

    @staticmethod
    def neighbourhood(netlist: Any) -> dict[str, list[str]]:
        """Which cells count as each cell's neighbours: every cell sharing a net, unless a subclass says otherwise."""
        return neighbours_of(netlist)

    # ----------------------------------------------------------- regions
    def region(self, trial: int) -> set[str]:
        placed = self.world.placements
        free = [c for c in placed if is_free(self.cells[c])]
        near = (
            sorted(
                {j for i in self.best_missing for j in self.neighbours[i] if j in free}
            )
            or free
        )
        if not near:
            return set()
        pivot = self.rng.choice(near)
        px, py = placed[pivot].x, placed[pivot].y
        radius = self.settings["radius"] + trial % self.settings["radius_cycle"]
        removed = {
            c for c in free if abs(placed[c].x - px) + abs(placed[c].y - py) < radius
        }
        if trial % self.settings["neighbor_cycle"] == 0:
            removed.update(near)
        if trial % self.settings["expand_cycle"] == 0:
            removed.update(
                j for i in tuple(removed) for j in self.neighbours[i] if j in free
            )
        return removed

    def prepare(self, trial: int) -> None:
        restart = (
            self.best_token is None
            or self.best_count <= len(self.cells) * self.settings["repair_threshold"]
            or trial % self.settings["restart_cycle"] == 0
        )
        if restart:
            if self.empty is not None:
                self.ctx.restore(self.empty)
            else:
                self.ctx.attempt(clear, label="clear")
            return
        self.ctx.restore(self.best_token)
        removed = sorted(self.region(trial) | set(self.best_missing))
        self.ctx.attempt(
            lambda b: [b.withdraw(c) for c in removed if c in b.placements],
            label="withdraw region",
        )
        for cell_id in self.best_missing:
            self.pressure[cell_id] = self.settings["repair_pressure"]

    # ------------------------------------------------------ construction
    def priority(self, cell_id: str, placed: Any, jitter: dict[str, float]) -> tuple:
        """Pinned cells first, then cells with a placed neighbour, by pressure, degree, size and jitter."""
        n = sum(j in placed for j in self.neighbours[cell_id])
        fp = self.world.footprint_of(cell_id)
        pinned = self.cells[cell_id].constraint.kind != "free"
        return (
            pinned,
            n > 0,
            self.pressure[cell_id] + n / (len(self.neighbours[cell_id]) or 1),
            n,
            fp.width * fp.height,
            jitter[cell_id],
        )

    def insert(self, builder: Any, cell_id: str, anchors: list[Any]) -> bool:
        """The first ``lookahead`` anchors that place are compared by routed wire cells; the cheapest stays, and with a lookahead of one the first that places stays as it is. ``insert_failures`` refusals end the scan."""
        lookahead = max(1, int(self.settings.get("lookahead", 1)))
        patience = int(self.settings.get("insert_failures", 8))
        best: tuple[int, Any] | None = None
        tried = 0
        refused = 0
        for anchor in anchors:
            if not builder.admits(cell_id, anchor.x, anchor.y, anchor.rot):
                continue
            if lookahead == 1:
                if builder.place(cell_id, anchor) is None:
                    self.proposals.occupy(cell_id, anchor.x, anchor.y, anchor.rot)
                    return True
                refused += 1
                if refused >= patience:
                    return False
                continue
            mark = builder.mark()
            if builder.place(cell_id, anchor) is None:
                cost = sum(
                    len(seg.cells)
                    for w in self.world.wires.values()
                    for seg in w.segments
                )
                if best is None or cost < best[0]:
                    best = (cost, anchor)
                tried += 1
            else:
                refused += 1
            builder.restore(mark)
            if tried >= lookahead or refused >= patience:
                break
        if best is None:
            return False
        anchor = best[1]
        if builder.place(cell_id, anchor) is None:
            self.proposals.occupy(cell_id, anchor.x, anchor.y, anchor.rot)
            return True
        return False

    def construct(self, builder: Any, trial: int) -> list[str]:
        """Insert every missing cell by priority; a refill round retries what failed with less clearance."""
        remaining = set(self.cells) - set(builder.placements)
        jitter = {c: self.rng.random() for c in self.cells}
        self.proposals.reset(self.settings["gap"] + trial % self.settings["gap_cycle"])
        failed: list[str] = []
        retries = 0
        while remaining:
            placed = builder.placements
            cell_id = max(
                sorted(remaining), key=lambda c: self.priority(c, placed, jitter)
            )
            remaining.remove(cell_id)
            if not self.insert(
                builder, cell_id, self.proposals.ranked(cell_id, trial, self.rng)
            ):
                failed.append(cell_id)
            if not remaining and failed and retries < self.settings["refill_rounds"]:
                remaining, failed, retries = set(failed), [], retries + 1
                self.proposals.reset(max(0, self.proposals.gap - 1))
        return failed

    def retain(self, failed: list[str]) -> None:
        """Pressure decays and the failed cells gain some; a new best by placed count is kept, and offered to the context so a budget that ends mid-trial still returns it."""
        for cell_id in self.cells:
            self.pressure[cell_id] *= self.settings["pressure_decay"]
        for cell_id in failed:
            self.pressure[cell_id] += self.settings["failure_pressure"]
        count = len(self.world.placements)
        if count > self.best_count or (
            count == self.best_count
            and self.rng.random() < self.settings["replace_equal"]
        ):
            self.best_count = count
            self.best_token = self.ctx.snapshot()
            self.best_missing = [
                c for c in self.cells if c not in self.world.placements
            ]
            self.ctx.consider(self.best_token)

    def complete(self) -> bool:
        return (
            len(self.world.placements) == len(self.cells) and not self.world.unrouted()
        )

    def run(self) -> bool:
        ctx = self.ctx
        for trial in range(self.settings["attempts"]):
            self.prepare(trial)
            failed: list[str] = []
            result = ctx.attempt(
                lambda b, t=trial, f=failed: f.extend(self.construct(b, t)),
                label=f"trial {trial}",
                strict=False,
            )
            if isinstance(result.refusal, Refusal):
                continue
            self.retain(failed)
            ctx.frame("trial")
            if self.complete():
                ctx.consider()
                return True
        if self.best_token is not None:
            ctx.restore(self.best_token)
        return False


__all__ = ["DEFAULTS", "Search", "clear", "neighbours_of"]
