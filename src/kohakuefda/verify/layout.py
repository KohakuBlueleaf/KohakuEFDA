"""A project layout judged by the framework: the reverse translation loaded into a world, then the runner."""

from kohakuefda.model.dataset import Dataset
from kohakuefda.model.layout import Layout
from kohakuefda.model.plan import Finding
from kohakuefda.synth.reverse import Reverse, project_names
from kohakulayout.engine import Context, metrics
from kohakulayout.verify import run


def check_layout(dataset: Dataset, layout: Layout) -> list[Finding]:
    """Every finding of the framework's runner over the layout, as the project's findings."""
    reverse = Reverse(dataset, layout)
    problem, kl_layout = reverse.problem()
    ctx = Context(problem, router=None)
    ctx.world.load(kl_layout)
    return [
        Finding(
            rule=f.rule,
            severity=f.severity,
            subject=project_names(reverse, f.subject),
            message=project_names(reverse, f.message),
        )
        for f in run(ctx.world, kl_layout, metrics(ctx.world))
    ]


__all__ = ["check_layout"]
