"""The trajectory: construct by regional repair, improve by moves; the next move starts from current, not best."""

from itertools import count
from typing import Any

from kohakulayout.engine.assessment import metrics
from kohakulayout.solvers.local.frontier import Frontier
from kohakulayout.solvers.local.moves import ConstructionMoves, LayoutMoves
from kohakulayout.solvers.local.policy import (
    Decision,
    decide,
    gaps,
    layout_delta,
    temperature,
)
from kohakulayout.solvers.regional.search import Search


class Trajectory:
    def __init__(
        self, ctx: Any, settings: dict[str, Any], method: str, search: type = Search
    ) -> None:
        self.ctx = ctx
        self.settings = settings
        self.method = method
        self.search = search
        self.accept_rng = ctx.rng
        self.board_area = ctx.world.fabric.width * ctx.world.fabric.height
        self.frontier = Frontier(ctx.world)
        self.phase_work = 0
        self.transitions = 0

    def steps(self, phase: str) -> Any:
        limit = self.settings[f"{phase}_steps"]
        budget = self.ctx.budget
        if (
            limit
            and self.settings["until_budget"]
            and (budget.units is not None or budget.seconds is not None)
        ):
            return count()
        return range(limit)

    def heat(self, phase: str) -> float:
        if self.method == "climb":
            return 0.0
        return temperature(
            self.settings[f"{phase}_temperature"],
            self.settings[f"{phase}_final_temperature"],
            self.ctx.budget.used - self.phase_work,
            self.settings[
                "layout_cooling_work" if phase == "layout" else "cooling_work"
            ],
        )

    def potential(self) -> float:
        return self.frontier.potential() if self.settings["frontier_weight"] else 0.0

    # ------------------------------------------------------- construction
    def construct(self) -> bool:
        ctx = self.ctx
        moves = ConstructionMoves(ctx, self.settings, self.search)
        self.phase_work = ctx.budget.used
        parent = metrics(ctx.world)
        parent_potential = self.potential()
        token = ctx.snapshot()
        for step in self.steps("construction"):
            if gaps(parent) == 0:
                break
            heat = self.heat("construction")
            name, body = moves.step(step)
            result = ctx.attempt(body, label=name)
            candidate = metrics(ctx.world)
            candidate_potential = self.potential()
            if result.refusal is not None or ctx.world.digest() == token.digest:
                decision, delta = Decision(False, 0.0), 0.0
            else:
                delta = (
                    gaps(candidate)
                    - gaps(parent)
                    + self.settings["frontier_weight"]
                    * (candidate_potential - parent_potential)
                )
                decision = decide(self.method, delta, heat, self.accept_rng)
            if decision.accepted:
                parent, parent_potential, token = (
                    candidate,
                    candidate_potential,
                    ctx.snapshot(),
                )
                ctx.consider(token)
            else:
                ctx.restore(token)
            self.transitions += 1
            ctx.frame("construct")
        return gaps(metrics(ctx.world)) == 0

    # -------------------------------------------------------- improvement
    def improve(self) -> None:
        ctx = self.ctx
        moves = LayoutMoves(ctx, self.settings, self.search)
        self.phase_work = ctx.budget.used
        parent = metrics(ctx.world)
        token = ctx.snapshot()
        ctx.consider(token)
        for _ in self.steps("improvement"):
            heat = self.heat("layout")
            name, body = moves.propose()
            if body is None:
                ctx.budget.charge(1)
                continue
            result = ctx.attempt(body, label=name)
            if result.refusal is not None or ctx.world.digest() == token.digest:
                if result.refusal is not None:
                    ctx.restore(token)
                self.transitions += 1
                continue
            candidate = metrics(ctx.world)
            if gaps(candidate) > 0:
                ctx.restore(token)
                continue
            delta = layout_delta(
                parent, candidate, self.board_area, self.settings["wire_tiebreak"]
            )
            decision = decide(self.method, delta, heat, self.accept_rng)
            if decision.accepted:
                parent, token = candidate, ctx.snapshot()
                ctx.consider(token)
            else:
                ctx.restore(token)
            self.transitions += 1
            ctx.frame("improve")


__all__ = ["Trajectory"]
