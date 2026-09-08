"""Level 3 for the floorplan solver on the gates toy and the bank fixture, within its bound."""

from importlib.resources import files

import pytest

from kohakulayout.engine import Budget
from kohakulayout.ir import Netlist
from kohakulayout.pipeline import solve
from kohakulayout.solvers import level3
from kohakulayout.state import StateCheck
from kohakulayout.templates.physics.gates import problem
from tests.kohakulayout.unit.solvers.test_level3_inorder import TOYS


def bank_toy():
    text = (
        files("kohakulayout.templates.physics.gates")
        .joinpath("fixtures/bank.kl")
        .read_text()
    )
    return problem(Netlist.parse(text), width=40, height=12)


@pytest.mark.parametrize("name", ["gates", "bank"])
def test_floorplan_passes_level3(name: str) -> None:
    toys = {"gates": TOYS["gates"], "bank": bank_toy}
    report = level3(
        "floorplan",
        {name: toys[name]},
        params={"steps": 40, "until_budget": False},
        units=20000,
    )
    assert report.failures == [], report.failures


def test_bank_answer_within_its_bound() -> None:
    result = solve(
        bank_toy(),
        solver="floorplan",
        seed=3,
        budget=Budget(units=6000),
        params={"steps": 40, "until_budget": False},
        checker=StateCheck(),
    )
    assert result.outcome == "complete" and result.assessment.valid
    assert result.assessment.metrics["area"] <= 40 * 12
    assert "k1/b1" in result.layout.placements
