"""Current-state HC/SA trajectories over shared coupled moves and legal gates."""

from itertools import count

from kohakuefda.framework.control import (
    BudgetExhausted,
    LocalBudgetExhausted,
    Rejected,
)
from kohakuefda.model.control import CancelledError
from kohakuefda.solvers.local.frontier import Frontier
from kohakuefda.solvers.local.moves import ConstructionMoves, LayoutMoves
from kohakuefda.solvers.local.policy import (
    Decision,
    decide,
    identity,
    layout_delta,
    missing,
    temperature,
)
from kohakuefda.solvers.regional import DEFAULTS as REGIONAL_DEFAULTS


class Trajectory:
    """Keep the actual current parent independent of best-state evidence."""

    def __init__(self, context, settings: dict, method: str) -> None:
        self.context = context
        self.settings = settings
        self.method = method
        self.accept_rng = context.rng("local.acceptance")
        self.current = None
        self.best = None
        self.phase_work = 0
        self.potentials = {}
        self.frontier = Frontier(context, REGIONAL_DEFAULTS)
        self.frame_every = int(context.world_settings["frame_every"])
        x0, y0, x1, y1 = context.area
        self.board_area = (x1 - x0) * (y1 - y0)

    def step_limit(self, phase: str) -> int | None:
        limit = self.settings[f"{phase}_steps"]
        budget = self.context.budget
        if (
            limit
            and self.settings["until_budget"]
            and (budget.seconds or budget.max_actions)
        ):
            return None
        return limit

    def steps(self, phase: str):
        limit = self.step_limit(phase)
        return count() if limit is None else range(limit)

    def work(self) -> int:
        counters = self.context.budget.work
        return counters["actions"] + counters["route_calls"]

    def heat(self, phase: str) -> float:
        if self.method == "hc":
            return 0.0
        return temperature(
            self.settings[f"{phase}_temperature"],
            self.settings[f"{phase}_final_temperature"],
            self.work() - self.phase_work,
            self.settings[
                "layout_cooling_work" if phase == "layout" else "cooling_work"
            ],
        )

    def choose(self, parent, candidate, phase, heat):
        if identity(parent) == identity(candidate):
            return 0.0, Decision(False, 0.0), "duplicate"
        if phase == "construction":
            delta = (
                missing(candidate)
                - missing(parent)
                + self.settings["frontier_weight"]
                * (self.potentials[candidate.id] - self.potentials[parent.id])
            )
        else:
            delta = layout_delta(
                dict(parent.assessment.metrics),
                dict(candidate.assessment.metrics),
                self.board_area,
                self.settings["wire_tiebreak"],
            )
        decision = decide(self.method, delta, heat, self.accept_rng)
        return delta, decision, "accepted" if decision.accepted else "rejected"

    def record(
        self,
        phase,
        step,
        operator,
        parent,
        candidate,
        heat,
        before,
        outcome,
        delta=None,
        decision=None,
    ):
        decision = decision or Decision(False, 0.0)
        ctx = self.context
        if decision.accepted:
            ctx.budget.work[
                "uphill_accepted" if delta > 0 else "nonuphill_accepted"
            ] += 1
        elif outcome == "duplicate":
            ctx.budget.work["duplicate_states"] += 1
        ctx.emit(
            "transition",
            {
                "method": self.method,
                "phase": phase,
                "step": step,
                "operator": operator,
                "parent": parent.id,
                "candidate": candidate.id if candidate else None,
                "next_parent": self.current.id,
                "best": self.best.id,
                "outcome": outcome,
                "delta": delta,
                "temperature": heat,
                "probability": decision.probability,
                "draw": decision.draw,
                "accepted": decision.accepted,
                "parent_potential": self.potentials.get(parent.id),
                "candidate_potential": (
                    self.potentials.get(candidate.id) if candidate else None
                ),
                "parent_missing": missing(parent),
                "candidate_missing": missing(candidate) if candidate else None,
                "parent_area": dict(parent.assessment.metrics)["area"],
                "candidate_area": (
                    dict(candidate.assessment.metrics)["area"] if candidate else None
                ),
                "area_delta": (
                    dict(candidate.assessment.metrics)["area"]
                    - dict(parent.assessment.metrics)["area"]
                    if candidate
                    else None
                ),
                "wire_delta": (
                    dict(candidate.assessment.metrics)["wire_path_cells"]
                    - dict(parent.assessment.metrics)["wire_path_cells"]
                    if candidate
                    else None
                ),
                "work": {k: v - before.get(k, 0) for k, v in ctx.budget.work.items()},
            },
        )
        if (
            outcome != "interrupted"
            and self.frame_every
            and step % self.frame_every == 0
        ):
            ctx.frame(
                "build" if phase == "construction" else "improve",
                method=self.method,
                step=step + 1,
                of=self.step_limit(
                    "construction" if phase == "construction" else "improvement"
                )
                or 0,
            )

    def construct(self) -> bool:
        ctx = self.context
        builder = ctx.builder()
        moves = ConstructionMoves(ctx, self.settings)
        self.current = self.best = builder.diagnostic()
        ctx.diagnostic = self.best
        self.potentials[self.current.id] = (
            self.frontier.potential() if self.settings["frontier_weight"] else 0.0
        )
        self.phase_work = self.work()
        for step in self.steps("construction"):
            ctx.budget.charge("construction_steps")
            parent = self.current
            heat = self.heat("construction")
            before = dict(ctx.budget.work)
            candidate = decision = delta = None
            outcome = "not_found"
            operator = "regional"
            try:
                with builder.transaction() as trial:
                    with ctx.budget.limit(
                        actions=self.settings["repair_actions"],
                        route_calls=self.settings["repair_route_calls"],
                    ):
                        if step and ctx.anchors:
                            operator = moves.prepare(step)
                        moves.fill(step)
                    candidate = trial.assess()
                    self.potentials[candidate.id] = (
                        self.frontier.potential()
                        if self.settings["frontier_weight"]
                        else 0.0
                    )
                    delta, decision, outcome = self.choose(
                        parent, candidate, "construction", heat
                    )
                    if decision.accepted:
                        trial.accept()
                if decision.accepted:
                    self.current = candidate
                if candidate is not None and (
                    missing(candidate),
                    *ctx.objective.key(candidate.assessment),
                ) < (missing(self.best), *ctx.objective.key(self.best.assessment)):
                    self.best = candidate
                    ctx.diagnostic = candidate
            except LocalBudgetExhausted:
                outcome = "repair_budget"
            except Rejected as error:
                outcome = error.status
            except (BudgetExhausted, CancelledError):
                self.record(
                    "construction",
                    step,
                    operator,
                    parent,
                    candidate,
                    heat,
                    before,
                    "interrupted",
                )
                raise
            if ctx.budget.work["actions"] == before.get("actions", 0):
                ctx.budget.charge("actions")
            self.record(
                "construction",
                step,
                operator,
                parent,
                candidate,
                heat,
                before,
                outcome,
                delta,
                decision,
            )
            self.potentials = {
                s.id: self.potentials[s.id] for s in (self.current, self.best)
            }
            if self.current.assessment.routed:
                builder.finish()
                return True
        return False

    def improve(self) -> None:
        ctx = self.context
        moves = LayoutMoves(ctx, self.settings)
        try:
            self.improve_with(moves)
        finally:
            moves.close()

    def improve_with(self, moves) -> None:
        ctx = self.context
        self.current = ctx.current
        self.best = ctx.best_routed
        self.phase_work = self.work()
        for step in self.steps("improvement"):
            ctx.budget.charge("improvement_steps")
            parent = ctx.current
            heat = self.heat("layout")
            before = dict(ctx.budget.work)
            operator, action = moves.propose()
            candidate = decision = delta = None
            issued = None
            outcome = "unsupported"
            try:
                if action is None:
                    ctx.budget.charge("actions")
                if action is not None:
                    with ctx.budget.limit(
                        actions=self.settings["repair_actions"],
                        route_calls=self.settings["repair_route_calls"],
                    ):
                        attempted = ctx.attempt(action)
                    outcome = attempted.status
                    issued = attempted.candidate
                    if issued is not None:
                        candidate = issued.snapshot
                        delta, decision, outcome = self.choose(
                            parent, candidate, "layout", heat
                        )
                        ctx.consider(candidate)
                        if decision.accepted:
                            ctx.accept(issued)
            except LocalBudgetExhausted:
                outcome = "repair_budget"
            except (BudgetExhausted, CancelledError):
                self.record(
                    "layout",
                    step,
                    operator,
                    parent,
                    candidate,
                    heat,
                    before,
                    "interrupted",
                )
                raise
            finally:
                if issued is not None:
                    ctx.discard(issued)
            self.current = ctx.current
            self.best = ctx.best_routed
            self.record(
                "layout",
                step,
                operator,
                parent,
                candidate,
                heat,
                before,
                outcome,
                delta,
                decision,
            )
