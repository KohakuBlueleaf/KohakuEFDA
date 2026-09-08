"""The context: attempts, the best archive, frames, scopes, the event digest."""

from kohakulayout.engine import Budget, Context, ListSink
from kohakulayout.engine.plugins import BudgetPlugin, DedupPlugin, FrameSampler
from kohakulayout.errors import BudgetExhausted
from kohakulayout.ir import Refusal
from kohakulayout.templates.physics.null import problem


def place_all(ctx: Context) -> None:
    for cell_id, x, y in (("box", 0, 0), ("c", 7, 7), ("t1", 3, 3), ("s1", 6, 3)):
        assert ctx.attempt(lambda b, c=cell_id, xy=(x, y): b.place(c, xy)).ok


def test_attempt_commits_or_rolls_back() -> None:
    sink = ListSink()
    ctx = Context(problem(), router=None, progress=sink)
    before = ctx.world.digest()
    result = ctx.attempt(lambda b: b.place("box", (9, 9)))
    assert result.refusal.stage == "region" and ctx.world.digest() == before
    assert sink.of("refusal")[0].payload.stage == "region"
    assert (
        ctx.attempt(
            lambda b: Refusal(stage="legal", subject="x", detail="a solver's own no")
        ).refusal.stage
        == "legal"
    )
    assert (
        ctx.attempt(lambda b: b.place("box", (0, 0))).ok
        and ctx.world.digest() != before
    )
    assert ctx.attempts == 3 and len(ctx.refusals) == 2


def test_consider_keeps_the_better_state() -> None:
    ctx = Context(problem(), router=None)
    place_all(ctx)
    first = ctx.consider()
    assert first is not None and ctx.best_assessment is first and ctx.accepts == 1
    token = ctx.snapshot()
    ctx.attempt(lambda b: b.withdraw("c"))
    worse = ctx.consider()
    assert worse is not None and worse.metrics["missing"] == 1
    assert ctx.best_assessment is first
    ctx.restore(token)
    assert ctx.consider() is first or ctx.assess().digest() == first.digest()
    assert ctx.restore_best() and ctx.world.digest() == ctx.best.digest
    assert ctx.best_layout().placements.keys() == ctx.world.placements.keys()


def test_frames_scopes_and_the_digest() -> None:
    def run(every: int) -> tuple[ListSink, Context]:
        sink = ListSink()
        ctx = Context(
            problem(),
            router=None,
            progress=sink,
            plugins=(BudgetPlugin(), FrameSampler(every=every), DedupPlugin()),
        )
        ctx.frame("start")
        with ctx.scope("construct", units=None):
            assert ctx.phase == "construct"
            for _ in range(4):
                ctx.frame("step")
        ctx.frame("end", layout=True)
        return sink, ctx

    sink, ctx = run(every=2)
    phases = [e.payload.phase for e in sink.of("frame")]
    assert phases == ["start", "step", "step", "end"] and ctx.phase == ""
    assert sink.of("frame")[-1].payload.layout is not None
    again, _ = run(every=2)
    assert again.digest() == sink.digest()
    ctx = Context(problem(), router=None, budget=Budget(units=10))
    try:
        with ctx.scope("tight", units=1):
            ctx.attempt(lambda b: b.place("box", (0, 0)))
            ctx.attempt(lambda b: b.place("c", (7, 7)))
    except BudgetExhausted as exc:
        assert "scope" in str(exc)
    assert ctx.budget.remaining is not None and ctx.budget.used <= 10
