"""The builder: the only door, charged per mutation, journaled through the world."""

import pytest

from kohakulayout.engine import Context
from kohakulayout.errors import StateError
from kohakulayout.ir import Layout
from kohakulayout.templates.physics.null import problem


def test_builder_charges_and_reports() -> None:
    ctx = Context(problem(), router=None)
    builder = ctx.builder()
    with pytest.raises(StateError, match="outside a transaction"):
        builder.place("box", (0, 0))
    result = ctx.attempt(lambda b: b.place("box", (0, 0)))
    assert result.ok and ctx.budget.used == 1
    assert builder.placements["box"].x == 0
    refused = ctx.attempt(lambda b: b.place("c", (1, 1)))
    assert not refused.ok and refused.refusal.stage == "overlap"
    assert builder.diagnostic().stage == "overlap"
    assert "c" in builder.unplaced() and builder.unrouted() == ("n1",)
    assert builder.extent() == (0, 0, 2, 2)
    assert builder.first_open("c").x == 2
    assert builder.admits("c", 2, 0) and not builder.admits("c", 0, 0)
    assert isinstance(builder.finish(), Layout)
    assert ctx.builder() is builder
