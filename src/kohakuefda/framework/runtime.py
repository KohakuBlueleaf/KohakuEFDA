"""Run any solver through shared lifecycle, budgets, evidence and observers."""

import json
import logging
import os
from typing import Protocol

from kohakuefda.framework.backend import SiteBackend, SiteCoverage, SiteRouting
from kohakuefda.framework.config import RUNTIME_DEFAULTS, settings_of
from kohakuefda.framework.context import Context
from kohakuefda.framework.control import Budget, BudgetExhausted, ConfigurationError
from kohakuefda.model.control import CancelledError
from kohakuefda.model.solver import Problem, Snapshot, SolveResult

log = logging.getLogger(__name__)


class Solver(Protocol):
    name: str
    capabilities: frozenset[str]

    def solve(self, context: Context) -> str: ...


class Runner:
    """Build a solver session once and execute it with injected mechanism implementations."""

    def __init__(
        self,
        problem: Problem,
        *,
        settings=None,
        world=None,
        actions=None,
        routing=None,
        coverage=None,
        objective=None,
        observe=None,
        cancelled=None,
    ) -> None:
        self.params = settings_of(RUNTIME_DEFAULTS, settings)
        params = self.params
        budget = Budget(cancelled, params["max_actions"], params["seconds"])
        self.backend = SiteBackend(
            problem, budget, world, params["backend"], routing, coverage
        )
        self.context = Context(
            self.backend, params["seed"], objective, actions, observe
        )
        self.context.workers = params["workers"] or min(16, os.process_cpu_count() or 1)
        self.context.backend_kind = params["backend"]
        self.context.forkable = (
            type(self.backend.routing) is SiteRouting
            and type(self.backend.coverage) is SiteCoverage
        )

    def run(
        self, solver: Solver, *, seed: Snapshot | None = None, strict: bool = True
    ) -> SolveResult:
        ctx, backend, params = self.context, self.backend, self.params
        missing = solver.capabilities - (backend.capabilities | set(ctx.actions))
        if missing:
            raise ConfigurationError(
                f"unsupported solver capabilities: {sorted(missing)}"
            )
        status, error = "completed", ""
        try:
            ctx.budget.check()
            ctx.frame("catalogue")
            if seed is not None:
                ctx.import_snapshot(seed)
            status = solver.solve(ctx)
            if status not in (
                "completed",
                "no_solution_found",
                "budget_exhausted",
                "cancelled",
            ):
                raise ConfigurationError(f"invalid solver stop reason {status!r}")
            if params["check_rates"]:
                ctx.budget.check()
                ctx.verify()
        except CancelledError:
            status = "cancelled"
        except BudgetExhausted:
            status = "budget_exhausted"
        except Exception as exc:
            if strict:
                raise
            log.exception("solver failed")
            status, error = "error", str(exc)
        current = ctx.current or ctx.diagnostic
        if current is not None:
            frame = backend.snapshot_frame(current, "final")
            frame["status"] = status
            ctx.emit("final", frame)
        resolved = {
            "runtime": params,
            "world": backend.settings,
            "solver": solver.name,
            "solver_settings": getattr(solver, "settings", {}),
            **backend.description(),
            "objective": ctx.objective.name,
        }
        return SolveResult(
            status,
            current,
            ctx.best_routed,
            ctx.best_verified,
            ctx.budget.elapsed,
            tuple(ctx.budget.work.items()),
            json.dumps(resolved, sort_keys=True),
            error,
        )


def solve(
    problem: Problem,
    solver: Solver,
    *,
    seed: Snapshot | None = None,
    strict: bool = True,
    **options,
) -> SolveResult:
    """Execute an injected strategy with common budgets, events and truthful evidence."""
    return Runner(problem, **options).run(solver, seed=seed, strict=strict)
