"""The framework metrics and the verdict, on the null instance."""

from kohakulayout.engine import Context, assess, metrics
from kohakulayout.ir import FRAMEWORK_METRICS, Assessment
from kohakulayout.state import StateCheck
from kohakulayout.templates.physics.null import problem


def test_metrics_follow_the_world() -> None:
    ctx = Context(problem(width=8, height=8), checker=StateCheck(), router=None)
    world = ctx.world
    empty = metrics(world)
    assert tuple(empty) == FRAMEWORK_METRICS
    assert (
        empty["placed"] == 0
        and empty["missing"] == 4
        and empty["unrouted"] == 1
        and empty["area"] == 0
    )
    with world.transaction() as tx:
        world.place("box", 0, 0)
        world.place("t1", 4, 4)
        tx.commit()
    after = metrics(world)
    assert (after["placed"], after["missing"]) == (2, 2)
    assert (after["extent_w"], after["extent_h"], after["area"]) == (5, 5, 25)


def test_assessment_is_truthful() -> None:
    ctx = Context(problem(width=8, height=8), router=None)
    world = ctx.world
    with world.transaction() as tx:
        for cell_id, x, y in (("box", 0, 0), ("c", 7, 7), ("t1", 3, 3), ("s1", 6, 3)):
            assert world.place(cell_id, x, y) is None
        tx.commit()
    assessment = ctx.assess()
    assert isinstance(assessment, Assessment)
    assert assessment.check() == []
    assert assessment.metrics["missing"] == 0 and assessment.metrics["unrouted"] == 1
    assert not assessment.complete and not assessment.valid
    assert [f.rule for f in assessment.findings] == ["kl.unrouted"]
    assert assessment.layout == ctx.layout().digest()
    assert assess(world, ctx.layout()).digest() == assessment.digest()
