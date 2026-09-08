"""Level 3 for the coordinate-level family on the gates toy, and the answer within its bound."""

import pytest

from kohakulayout.engine import Budget
from kohakulayout.pipeline import solve
from kohakulayout.solvers import known, level3
from kohakulayout.state import StateCheck
from tests.kohakulayout.unit.solvers.test_level3_inorder import TOYS

AREA_BOUND = 120
QUICK = {
    "baseline": {"shrink_rounds": 20},
    "regional": {"attempts": 16, "shrink_rounds": 20},
    "climb": {"improvement_steps": 150, "until_budget": False},
    "anneal": {"improvement_steps": 150, "until_budget": False},
}


@pytest.mark.parametrize("solver", sorted(QUICK))
def test_family_passes_level3(solver: str) -> None:
    assert solver in known()
    report = level3(solver, {"gates": TOYS["gates"]}, params=QUICK[solver], units=20000)
    assert report.failures == [], report.failures


@pytest.mark.parametrize("solver", ("baseline", "climb"))
def test_gates_answer_within_its_bound(solver: str) -> None:
    result = solve(
        TOYS["gates"](),
        solver=solver,
        seed=7,
        budget=Budget(units=6000),
        params=QUICK[solver],
        checker=StateCheck(),
    )
    assert result.outcome == "complete" and result.assessment.valid
    assert result.assessment.metrics["area"] <= AREA_BOUND
