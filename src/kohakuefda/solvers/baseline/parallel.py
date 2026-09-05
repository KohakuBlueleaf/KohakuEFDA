"""Baseline-owned attempt slicing and deterministic winner selection."""

from kohakuefda.framework.runtime import Runner
from kohakuefda.solvers.baseline.spread import Spread

PRIME = 7919


class Construct:
    name = "baseline-construction-v1"
    capabilities = frozenset({"place"})

    def __init__(self, settings):
        self.settings = settings
        self.spread = None

    def solve(self, context):
        self.spread = Spread(context, self.settings)
        return "completed" if self.spread.run() else "no_solution_found"


def construct(problem, settings, world, seed, backend, seconds):
    solver = Construct(settings)
    runner = Runner(
        problem,
        settings={
            "seed": seed,
            "backend": backend,
            "seconds": seconds,
            "check_rates": False,
        },
        world=world,
    )
    result = runner.run(solver)
    return result, tuple(solver.spread.order), solver.spread.tried


def build_parallel(context, settings):
    """Return the selected spread order, or None when all slices fail."""
    size, limit = settings["spread_slice"], settings["spread_attempts"]
    best = None
    for start in range(0, limit, size * context.workers):
        context.budget.check()
        remaining = (
            max(0.001, context.budget.seconds - context.budget.elapsed)
            if context.budget.seconds
            else 0.0
        )
        jobs = tuple(
            (
                context.problem,
                {**settings, "spread_attempts": min(size, limit - offset)},
                context.world_settings,
                context.seed + offset * PRIME,
                context.backend_kind,
                remaining,
            )
            for offset in range(start, min(limit, start + size * context.workers), size)
        )
        results = context.gather(construct, jobs)
        for result, _, _ in results:
            context.budget.work.update(dict(result.work))
        for result, order, tried in results:
            snapshot = result.current
            if snapshot is None:
                continue
            if snapshot.assessment.routed:
                context.import_snapshot(snapshot)
                context.frame("build", attempt=tried)
                return order
            score = sum(i.rule == "layout.unplaced" for i in snapshot.assessment.issues)
            if best is None or score < best[0]:
                best = score, snapshot
    if best is not None:
        context.diagnostic = best[1]
    return None
