"""Problem in, layout and assessment out: the one function a project calls when it wants an answer."""

from dataclasses import dataclass, field
from typing import Any

from kohakulayout.engine import Budget, Context, ListSink, make_execution
from kohakulayout.engine.checkpoint import Checkpoint
from kohakulayout.ir import Assessment, Layout, Problem
from kohakulayout.pipeline.passes import DEFAULT_PASSES, PassManager
from kohakulayout.solvers import Outcome, get


@dataclass
class Result:
    outcome: Outcome
    layout: Layout
    assessment: Assessment
    checkpoints: list[Checkpoint] = field(default_factory=list)
    events: ListSink | None = None
    context: Any = None
    refusals: int = 0
    attempts: int = 0


def solve(
    problem: Problem,
    solver: str = "inorder",
    seed: int = 0,
    budget: Budget | None = None,
    params: dict[str, Any] | None = None,
    plugins: Any = None,
    progress: Any = None,
    router: Any = "default",
    kernel: str = "python",
    checker: Any = None,
    passes: tuple[Any, ...] = DEFAULT_PASSES,
    run: str | None = None,
    workers: int = 1,
) -> Result:
    """Run the passes, then the solver on a context; the best layout and its assessment come back."""
    problem = PassManager(passes).run(problem)
    sink = progress if progress is not None else ListSink()
    ctx = Context(
        problem,
        seed=seed,
        kernel=kernel,
        router=router,
        checker=checker,
        budget=budget,
        plugins=plugins,
        progress=sink,
        run=run,
        execution=make_execution(workers),
    )
    outcome = get(solver).run(ctx, **(params or {}))
    layout = ctx.best_layout()
    assessment = (
        ctx.best_assessment if ctx.best_assessment is not None else ctx.assess()
    )
    return Result(
        outcome=outcome,
        layout=layout,
        assessment=assessment,
        checkpoints=list(ctx.checkpoints),
        events=sink if isinstance(sink, ListSink) else None,
        context=ctx,
        refusals=len(ctx.refusals),
        attempts=ctx.attempts,
    )


__all__ = ["Result", "solve"]
