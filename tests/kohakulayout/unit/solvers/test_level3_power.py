"""Level 3 on the power variant for the null solver and hill climbing."""

from importlib.resources import files

import pytest

from kohakulayout.engine import Budget
from kohakulayout.ir import Netlist
from kohakulayout.pipeline import solve
from kohakulayout.solvers import level3
from kohakulayout.state import StateCheck
from kohakulayout.templates.physics.gates import problem


def power_toy():
    text = (
        files("kohakulayout.templates.physics.gates")
        .joinpath("fixtures/and_or_not_power.kl")
        .read_text()
    )
    return problem(Netlist.parse(text), power=True, width=24, height=12)


@pytest.mark.parametrize(
    ("solver", "params"),
    [("inorder", {}), ("climb", {"improvement_steps": 100, "until_budget": False})],
)
def test_power_variant_passes_level3(solver: str, params: dict) -> None:
    report = level3(solver, {"power": power_toy}, params=params, units=20000)
    assert report.failures == [], report.failures


def test_power_answer_carries_emitters() -> None:
    result = solve(
        power_toy(),
        solver="baseline",
        seed=3,
        budget=Budget(units=6000),
        params={"shrink_rounds": 10},
        checker=StateCheck(),
    )
    assert result.outcome == "complete" and result.assessment.valid
    assert result.assessment.metrics["emitters"] >= 1
    assert all(
        u.owner == "field:power"
        for u in result.layout.units.values()
        if u.footprint == "VDD"
    )
