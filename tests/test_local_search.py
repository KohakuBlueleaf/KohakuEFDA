"""Actual coupled HC/SA trajectories, legality and independent best-state evidence."""

import json
import math
import random
from itertools import pairwise
from pathlib import Path

import pytest

from kohakuefda.framework import problem_of
from kohakuefda.framework.control import ConfigurationError
from kohakuefda.framework.runtime import Runner
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.scenario import Scenario
from kohakuefda.plan.netlist import build_netlist
from kohakuefda.plan.planner import plan
from kohakuefda.route.pathfinder import NATIVE
from kohakuefda.solvers.local import HillClimbing, SimulatedAnnealing
from kohakuefda.solvers.local.policy import decide, missing, temperature

ROOT = Path(__file__).resolve().parents[1]
BACKENDS = ["python"] + (["native"] if NATIVE else [])
ZERO = {
    "construction_temperature": 0,
    "construction_final_temperature": 0,
    "layout_temperature": 0,
    "layout_final_temperature": 0,
}


@pytest.fixture(scope="module")
def dataset():
    return Dataset.load(ROOT / "data/1.5.3@9764758-3/dataset.json")


def make_problem(dataset, name):
    scenario = Scenario.from_toml(ROOT / "tests/fixtures" / f"scenario_{name}.toml")
    planned = plan(dataset, scenario)
    return problem_of(dataset, build_netlist(dataset, scenario, planned), planned)


@pytest.fixture(scope="module")
def problem(dataset):
    return make_problem(dataset, "valley_battery")


def run(problem, solver, backend="native", seed=0, **runtime):
    events = []
    runner = Runner(
        problem,
        settings={"backend": backend, "check_rates": False, "seed": seed, **runtime},
        observe=events.append,
    )
    result = runner.run(solver)
    rows = [json.loads(e.payload_json) for e in events if e.kind == "transition"]
    return result, rows


def assert_lineage(rows):
    for row in rows:
        expected = row["candidate"] if row["accepted"] else row["parent"]
        assert row["next_parent"] == expected
    for before, after in pairwise(rows):
        if before["phase"] == after["phase"]:
            assert before["next_parent"] == after["parent"]


@pytest.mark.parametrize("backend", BACKENDS)
def test_hc_and_sa_use_real_current_parents_and_keep_complete_best(problem, backend):
    hc, hc_rows = run(problem, HillClimbing(improvement_steps=200), backend)
    sa, sa_rows = run(problem, SimulatedAnnealing(improvement_steps=200), backend)
    for result, rows in ((hc, hc_rows), (sa, sa_rows)):
        assert result.status == "completed"
        assert result.current.assessment.routed
        assert result.best_routed.assessment.routed
        assert result.best_verified is None
        assert_lineage(rows)
        assert any(row["outcome"] == "not_found" for row in rows)
        assert any(row["accepted"] and row["delta"] == 0 for row in rows)
        assert all(
            row["candidate_missing"] == 0
            for row in rows
            if row["phase"] == "layout" and row["accepted"]
        )
        area = dict(result.best_routed.assessment.metrics)["area"]
        assert area <= min(
            row["candidate_area"] for row in rows if row["candidate_area"] is not None
        )
    assert not any(row["accepted"] and row["delta"] > 0 for row in hc_rows)
    assert any(row["accepted"] and row["delta"] > 0 for row in sa_rows)
    assert any(
        row["delta"] is not None and row["delta"] > 0 and not row["accepted"]
        for row in sa_rows
    )
    assert hc_rows[0]["candidate"] == sa_rows[0]["candidate"]


@pytest.mark.parametrize("backend", BACKENDS)
def test_zero_temperature_sa_is_hc_with_identical_proposal_stream(problem, backend):
    hc, hc_rows = run(problem, HillClimbing(improvement_steps=100), backend)
    sa, sa_rows = run(
        problem, SimulatedAnnealing(improvement_steps=100, **ZERO), backend
    )
    assert hc.current == sa.current
    assert hc.best_routed == sa.best_routed
    assert hc.work == sa.work
    stripped = lambda rows: [
        {k: v for k, v in row.items() if k != "method"} for row in rows
    ]
    assert stripped(hc_rows) == stripped(sa_rows)


@pytest.mark.parametrize("solver", [HillClimbing, SimulatedAnnealing])
def test_work_capped_runs_are_reproducible_and_seed_changes_trajectory(problem, solver):
    first, rows = run(
        problem, solver(improvement_steps=200), BACKENDS[-1], max_actions=100
    )
    second, replay = run(
        problem, solver(improvement_steps=200), BACKENDS[-1], max_actions=100
    )
    assert first.status == second.status == "budget_exhausted"
    assert first.current == second.current
    assert first.work == second.work
    assert rows == replay
    other, _ = run(
        problem, solver(improvement_steps=200), BACKENDS[-1], seed=1, max_actions=100
    )
    assert first.current.id != other.current.id


@pytest.mark.skipif(not NATIVE, reason="dense construction uses native routing")
def test_sa_accepts_incomplete_uphill_states_without_publishing_them(dataset):
    problem = make_problem(dataset, "dense_valley12")
    options = {
        "construction_steps": 20,
        "candidates": 10,
        "improvement_steps": 0,
        "construction_temperature": 20,
        "construction_final_temperature": 20,
    }
    result, rows = run(problem, SimulatedAnnealing(**options))
    assert_lineage(rows)
    assert result.best_routed is None
    assert not result.current.assessment.routed
    uphill = [row for row in rows if row["accepted"] and row["delta"] > 0]
    assert uphill
    assert all(row["candidate_missing"] > row["parent_missing"] for row in uphill)
    assert missing(result.current) == min(
        row["candidate_missing"] for row in rows if row["candidate_missing"] is not None
    )
    assert rows[-1]["next_parent"] != result.current.id


def test_scoped_repair_budget_ends_proposal_not_whole_search(problem):
    result, rows = run(
        problem, HillClimbing(construction_steps=3, repair_actions=1), BACKENDS[-1]
    )
    assert result.status == "no_solution_found"
    assert len(rows) == 3
    assert all(row["outcome"] == "repair_budget" for row in rows)
    assert_lineage(rows)
    assert dict(result.work)["actions"] == 3
    assert result.best_routed is None


@pytest.mark.parametrize("solver", [HillClimbing, SimulatedAnnealing])
def test_imported_seed_skips_construction_and_moves_remain_routed(problem, solver):
    seed, _ = run(problem, HillClimbing(improvement_steps=0), BACKENDS[-1])
    events = []
    result = Runner(
        problem,
        settings={"backend": BACKENDS[-1], "check_rates": False},
        observe=events.append,
    ).run(solver(improvement_steps=60), seed=seed.current)
    assert result.current.assessment.routed
    assert dict(result.work).get("construction_steps", 0) == 0
    assert not any(e.kind == "constructed" for e in events)
    frames = [json.loads(e.payload_json) for e in events if e.kind == "improve"]
    assert frames and all(frame["clean"] for frame in frames)
    assert (
        dict(result.best_routed.assessment.metrics)["area"]
        <= dict(seed.current.assessment.metrics)["area"]
    )


def test_acceptance_and_work_cooling():
    rng = random.Random(0)
    assert decide("hc", 1, 1000, rng).accepted is False
    assert decide("sa", 1, 0, rng).accepted is False
    assert decide("hc", 0, 0, rng).accepted
    assert decide("sa", -1, 1, rng).accepted
    decision = decide("sa", 2, 4, rng)
    assert decision.probability == pytest.approx(math.exp(-0.5))
    assert decision.accepted == (decision.draw < decision.probability)
    assert temperature(2, 0.02, 0, 100) == 2
    assert temperature(2, 0.02, 50, 100) == pytest.approx(0.2)
    assert temperature(2, 0.02, 1000, 100) == 0.02


@pytest.mark.parametrize(
    "settings",
    [
        {"cooling_work": 0},
        {"candidates": 0},
        {"repair_actions": 0},
        {"layout_temperature": 0},
        {"layout_final_temperature": 10},
        {"construction_temperature": float("inf")},
    ],
)
def test_local_policy_settings_are_validated(settings):
    with pytest.raises(ConfigurationError):
        SimulatedAnnealing(**settings)
