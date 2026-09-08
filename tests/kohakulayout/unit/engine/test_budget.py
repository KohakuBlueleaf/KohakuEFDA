"""The budget: caps, scopes, the clock, and the one-charge overshoot."""

import pytest

from kohakulayout.engine import Budget
from kohakulayout.errors import BudgetExhausted


def test_units_cap_names_its_knob() -> None:
    budget = Budget(units=3)
    for _ in range(3):
        budget.charge()
    assert budget.remaining == 0 and budget.exhausted()
    with pytest.raises(BudgetExhausted, match="raise units"):
        budget.charge()
    assert budget.used == 4 and budget.charges == 4


def test_scoped_limit_leaves_the_outer_budget() -> None:
    budget = Budget(units=10)
    with budget.limit(2), pytest.raises(BudgetExhausted, match="scope"):
        budget.charge(3)
    assert budget.remaining == 7
    budget.charge(7)
    assert budget.exhausted()


def test_seconds_use_the_clock() -> None:
    now = [0.0]
    budget = Budget(seconds=1.0, clock=lambda: now[0])
    budget.charge()
    now[0] = 2.0
    assert budget.exhausted()
    with pytest.raises(BudgetExhausted, match="seconds"):
        budget.charge()
    assert Budget().remaining is None and not Budget().exhausted()
    assert Budget(units=5).snapshot()["units"] == 5
