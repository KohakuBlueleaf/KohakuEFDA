"""Seeded spread slices across the execution slot; the first complete slice wins, else the best partial."""

from typing import Any

from kohakulayout.engine.budget import Budget
from kohakulayout.engine.context import Context
from kohakulayout.ir import Layout, Problem
from kohakulayout.physics import locate, path_of
from kohakulayout.solvers.baseline.spread import Spread

PRIME = 7919


def construct_slice(
    problem_json: str,
    physics_path: str,
    settings: dict[str, Any],
    seed: int,
    router: str,
) -> tuple[tuple[int, int], str]:
    """One worker's slice: a fresh context, a spread run, the layout and its score as JSON."""
    problem = Problem.from_json(problem_json)
    physics = locate(physics_path)()
    ctx = Context(
        problem,
        physics=physics,
        seed=seed,
        router=router,
        budget=Budget(seconds=settings.get("seconds")),
    )
    spread = Spread(ctx, settings)
    spread.run()
    world = ctx.world
    score = (len(world.netlist.cells) - len(world.placements), len(world.unrouted()))
    return score, world.freeze().to_json()


def build_parallel(ctx: Any, settings: dict[str, Any], router: str = "default") -> bool:
    """Slices of ``spread_slice`` attempts per worker until one completes; loads the winner into the context."""
    size, limit = settings["spread_slice"], settings["spread_attempts"]
    workers = max(1, ctx.execution.workers)
    problem_json, physics_path = ctx.problem.to_json(), path_of(ctx.physics)
    best: tuple[tuple[int, int], str] | None = None
    for start in range(0, limit, size * workers):
        remaining = None
        if ctx.budget.seconds is not None:
            remaining = max(0.001, ctx.budget.seconds - ctx.budget.elapsed)
        tasks = [
            (
                construct_slice,
                (
                    problem_json,
                    physics_path,
                    {
                        **settings,
                        "spread_attempts": min(size, limit - offset),
                        "seconds": remaining,
                    },
                    ctx.seed + offset * PRIME,
                    router,
                ),
            )
            for offset in range(start, min(limit, start + size * workers), size)
        ]
        for score, layout_json in ctx.gather(tasks):
            ctx.budget.charge(size)
            if best is None or score < best[0]:
                best = (score, layout_json)
            if score == (0, 0):
                ctx.world.load(Layout.from_json(layout_json))
                ctx.consider()
                ctx.frame("spread")
                return True
    if best is not None:
        ctx.world.load(Layout.from_json(best[1]))
    return False


__all__ = ["PRIME", "build_parallel", "construct_slice"]
