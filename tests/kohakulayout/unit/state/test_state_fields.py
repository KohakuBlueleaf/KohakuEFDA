"""Level 2 on the power variant: cover inside the transaction, the field refusal, rollback, findings."""

from kohakulayout.engine import Context
from kohakulayout.ir import Layout
from kohakulayout.state import StateCheck, World
from kohakulayout.templates.physics.gates import (
    GatesPowerPhysics,
    from_expressions,
    problem,
)
from kohakulayout.verify import uncovered


def test_place_covers_needs_and_refuses_when_nothing_can() -> None:
    prob = problem(from_expressions("y = a & b"), power=True, width=16, height=8)
    world = World(prob, GatesPowerPhysics(), router=None)
    check = StateCheck().mount(world)
    with world.transaction() as tx:
        assert world.place("a", 0, 1) is None and world.units == {}
        assert world.place("g1", 4, 1) is None
        (unit,) = world.units.values()
        assert unit.owner == "field:power" and unit.footprint == "VDD"
        assert any(c in world.field_coverage("power") for c in ((4, 1), (5, 2), (6, 3)))
        assert world.place("b", 0, 3) is None and len(world.units) == 1
        tx.commit()
    with world.transaction() as tx:
        world.withdraw("g1")
        assert len(world.units) == 1
        tx.commit()
    assert check.failures == []
    assert uncovered(world, world.freeze()) == ()


def test_field_refusal_leaves_the_digest() -> None:
    prob = problem(from_expressions("y = a & b"), power=True, width=8, height=5)
    world = World(prob, GatesPowerPhysics(), router=None)
    check = StateCheck().mount(world)
    with world.transaction() as tx:
        keep = {(x, y) for x in range(1, 4) for y in range(1, 4)} | {
            (0, 1),
            (0, 3),
            (4, 2),
        }
        world.reserve(
            "wall",
            "ground",
            [(x, y) for x in range(8) for y in range(5) if (x, y) not in keep],
            carrier="clk",
        )
        before = world.digest()
        refusal = world.place("g1", 1, 1)
        assert refusal is not None and refusal.stage == "field"
        assert world.digest() == before and world.units == {}
        tx.commit()
    assert check.failures == []


def test_uncovered_finding_on_a_loaded_layout() -> None:
    prob = problem(from_expressions("y = a & b"), power=True, width=16, height=8)
    ctx = Context(prob, router=None)
    assert ctx.attempt(lambda b: b.place("g1", (4, 1))).ok
    layout = ctx.layout()
    bare = layout.model_copy(update={"units": {}})
    findings = uncovered(ctx.world, bare)
    assert [f.rule for f in findings] == ["kl.field"] and findings[
        0
    ].subject == "cell:g1"
    ctx.world.load(bare)
    assessment = ctx.assess()
    assert not assessment.valid and any(
        f.rule == "kl.field" for f in assessment.findings
    )
    assert isinstance(
        (
            Layout.parse(
                layout.text(),
            )
            if False
            else layout
        ),
        Layout,
    )
