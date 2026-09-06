"""Budget-driven trajectories, transaction-safe repacking and persistent best evidence."""

import json
import random
from dataclasses import replace
from itertools import pairwise
from pathlib import Path

import pytest

from kohakuefda.framework import ConfigurationError, Scope, problem_of
from kohakuefda.framework.control import LocalBudgetExhausted
from kohakuefda.framework.runtime import Runner
from kohakuefda.model.cells import Netlist
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.scenario import Scenario
from kohakuefda.plan.netlist import build_netlist
from kohakuefda.plan.planner import plan
from kohakuefda.route.pathfinder import NATIVE
from kohakuefda.solvers.local import DEFAULTS, HillClimbing, SimulatedAnnealing
from kohakuefda.solvers.local.repack import ACTION, RepackMoves

ROOT = Path(__file__).resolve().parents[1]
BACKENDS = ["python"] + (["native"] if NATIVE else [])


@pytest.fixture(scope="module")
def dataset():
    return Dataset.load(ROOT / "data/1.5.3@9764758-3/dataset.json")


@pytest.fixture(scope="module")
def problem(dataset):
    scenario = Scenario.from_toml(ROOT / "tests/fixtures/scenario_valley_battery.toml")
    planned = plan(dataset, scenario)
    return problem_of(dataset, build_netlist(dataset, scenario, planned), planned)


@pytest.fixture(scope="module")
def seed(problem):
    result = Runner(problem, settings={"check_rates": False}).run(
        HillClimbing(improvement_steps=0)
    )
    assert result.current.assessment.routed
    return result.current


def run(problem, seed, backend, solver, cap, **options):
    events, best_areas = [], []

    def observe(event):
        if event.kind == "transition":
            events.append(json.loads(event.payload_json))
            best_areas.append(
                dict(runner.context.best_routed.assessment.metrics)["area"]
            )

    runner = Runner(
        problem,
        settings={"backend": backend, "check_rates": False, "max_actions": cap},
        observe=observe,
    )
    result = runner.run(solver(improvement_steps=2, **options), seed=seed)
    assert ACTION not in runner.context.actions
    return result, events, best_areas


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("solver", [HillClimbing, SimulatedAnnealing])
def test_more_work_extends_the_same_trajectory_beyond_default_steps(
    problem, seed, backend, solver
):
    short, short_rows, short_best = run(problem, seed, backend, solver, 100)
    long, long_rows, long_best = run(problem, seed, backend, solver, 400)
    assert short.status == long.status == "budget_exhausted"
    assert dict(long.work)["improvement_steps"] > 2
    assert dict(short.work)["actions"] == 100
    assert dict(long.work)["actions"] == 400
    prefix = [row for row in short_rows if row["outcome"] != "interrupted"]
    assert long_rows[: len(prefix)] == prefix
    for best in (short_best, long_best):
        assert all(b <= a for a, b in pairwise(best))
    assert (
        dict(long.best_routed.assessment.metrics)["area"]
        <= dict(short.best_routed.assessment.metrics)["area"]
    )
    assert all(a["next_parent"] == b["parent"] for a, b in pairwise(long_rows))
    assert long.current.assessment.routed
    fixed, rows, _ = run(problem, seed, backend, solver, 400, until_budget=False)
    assert fixed.status == "completed"
    assert len(rows) == 2


@pytest.mark.parametrize("backend", BACKENDS)
def test_repacking_is_scoped_complete_and_restores_rejected_candidates(
    problem, seed, backend
):
    ctx = Runner(problem, settings={"backend": backend, "check_rates": False}).context
    ctx.import_snapshot(seed)
    moves = RepackMoves(ctx, DEFAULTS, random.Random(0))
    try:
        before = ctx.current
        action = moves.repack()
        assert action.name == ACTION
        result = ctx.attempt(replace(action, scope=Scope(frozenset())))
        assert result.status == "scope_required"
        assert ctx.current == before
        successes = 0
        for _ in range(30):
            result = ctx.attempt(moves.repack())
            assert ctx.current == before
            if result.candidate:
                assert result.candidate.snapshot.assessment.routed
                successes += 1
                ctx.discard(result.candidate)
        assert successes > 0
        with pytest.raises(LocalBudgetExhausted), ctx.budget.limit(actions=1):
            ctx.attempt(moves.repack())
        assert ctx.current == before
        assert not ctx.view.unrouted
    finally:
        moves.close()
    assert ACTION not in ctx.actions


def test_repack_registration_cannot_replace_an_existing_action(problem, seed):
    ctx = Runner(problem, settings={"check_rates": False}).context
    ctx.import_snapshot(seed)
    first = RepackMoves(ctx, DEFAULTS, random.Random(0))
    try:
        with pytest.raises(ConfigurationError, match="already registered"):
            RepackMoves(ctx, DEFAULTS, random.Random(1))
        assert ctx.actions[ACTION] is first.handler
    finally:
        first.close()
    first.close()
    assert ACTION not in ctx.actions


def test_no_available_moves_still_exhaust_the_global_action_budget(dataset):
    scenario = Scenario.from_toml(ROOT / "tests/fixtures/scenario_valley_battery.toml")
    empty = Netlist(
        dataset_version=dataset.version.id, scenario=scenario, plan_status="ok"
    )
    problem = problem_of(dataset, empty)
    runner = Runner(problem, settings={"check_rates": False, "max_actions": 7})
    result = runner.run(HillClimbing(improvement_steps=1))
    assert result.status == "budget_exhausted"
    assert result.best_routed.assessment.routed
    assert dict(result.work)["actions"] == 7
    assert dict(result.work)["improvement_steps"] > 1
    assert ACTION not in runner.context.actions


def test_zero_improvement_steps_remains_an_explicit_skip(problem):
    result = Runner(problem, settings={"seconds": 10, "check_rates": False}).run(
        HillClimbing(improvement_steps=0)
    )
    assert result.status == "completed"
    assert result.current.assessment.routed
    assert dict(result.work).get("improvement_steps", 0) == 0
