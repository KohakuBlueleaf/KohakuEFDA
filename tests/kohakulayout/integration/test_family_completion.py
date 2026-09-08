"""The coordinate family completes circuits the in-order stream leaves incomplete."""

import pytest

from kohakulayout.engine import Budget
from kohakulayout.pipeline import solve
from kohakulayout.templates.physics.gates import problem, random_circuit

HARD_SEEDS = (3, 7)
PARAMS = {
    "baseline": {"shrink_rounds": 10},
    "regional": {"attempts": 16, "shrink_rounds": 10},
    "climb": {"improvement_steps": 60, "until_budget": False},
    "anneal": {"improvement_steps": 60, "until_budget": False},
}


@pytest.mark.parametrize("seed", HARD_SEEDS)
def test_inorder_leaves_the_hard_circuits_incomplete(seed: int) -> None:
    result = solve(
        problem(random_circuit(seed, inputs=4, gates=8), width=48, height=24),
        solver="inorder",
        seed=seed,
        budget=Budget(units=4000),
    )
    assert result.outcome != "complete"


@pytest.mark.parametrize("solver", sorted(PARAMS))
@pytest.mark.parametrize("seed", HARD_SEEDS)
def test_family_completes_the_hard_circuits(solver: str, seed: int) -> None:
    result = solve(
        problem(random_circuit(seed, inputs=4, gates=8), width=48, height=24),
        solver=solver,
        seed=seed,
        budget=Budget(units=4000),
        params=PARAMS[solver],
    )
    assert result.outcome == "complete", result.outcome
    assert result.assessment.valid
    assert result.assessment.metrics["missing"] == 0
    assert result.assessment.metrics["unrouted"] == 0
