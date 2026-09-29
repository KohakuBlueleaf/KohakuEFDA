"""Batched leaf placement preserves routing, rollback and charged action limits."""

import pytest

from kohakulayout.engine import Budget, Context
from kohakulayout.errors import BudgetExhausted, StateError
from kohakulayout.physics.protocol import Anchor
from kohakulayout.state import StateCheck
from kohakulayout.templates.physics.null import problem


@pytest.mark.parametrize("kernel", ["python", "auto"])
def test_batch_routes_after_all_footprints_are_present(kernel: str) -> None:
    ctx = Context(problem(), kernel=kernel)
    anchors = {
        "t1": Anchor(x=0, y=0),
        "s1": Anchor(x=5, y=0),
        "box": Anchor(x=2, y=3),
        "c": Anchor(x=6, y=6),
    }
    result = ctx.attempt(lambda builder: builder.place_batch(anchors))
    assert result.ok
    assert ctx.budget.used == len(anchors)
    assert set(ctx.world.placements) == set(anchors)
    assert set(ctx.world.wires) == {"n1"}
    assert ctx.assess().valid and ctx.assess().complete


def test_overlap_rolls_back_every_leaf_and_route() -> None:
    ctx = Context(problem())
    before = ctx.world.digest()
    result = ctx.attempt(
        lambda builder: builder.place_batch(
            {
                "t1": Anchor(x=0, y=0),
                "s1": Anchor(x=5, y=0),
                "box": Anchor(x=3, y=3),
                "c": Anchor(x=3, y=3),
            }
        )
    )
    assert not result.ok
    assert ctx.world.digest() == before
    assert ctx.budget.used == 4


def test_budget_exception_does_not_leave_successful_batch_in_the_world() -> None:
    ctx = Context(problem(), budget=Budget(units=1))
    before = ctx.world.digest()
    with pytest.raises(BudgetExhausted):
        ctx.attempt(
            lambda builder: builder.place_batch(
                {
                    "box": Anchor(x=0, y=0),
                    "c": Anchor(x=4, y=4),
                }
            )
        )
    assert ctx.world.digest() == before


def test_invalid_leaf_is_rejected_before_mutation() -> None:
    ctx = Context(problem())
    before = ctx.world.digest()
    with pytest.raises(StateError):
        ctx.attempt(
            lambda builder: builder.place_batch(
                {
                    "box": Anchor(x=0, y=0),
                    "missing": Anchor(x=4, y=4),
                }
            )
        )
    assert ctx.world.digest() == before


def test_checked_batch_uses_the_checker_and_remains_atomic() -> None:
    ctx = Context(problem(), checker=StateCheck())
    result = ctx.attempt(
        lambda builder: builder.place_batch(
            {
                "box": Anchor(x=0, y=0),
                "c": Anchor(x=4, y=4),
            }
        )
    )
    assert result.ok
    assert len(ctx.world.placements) == 2
