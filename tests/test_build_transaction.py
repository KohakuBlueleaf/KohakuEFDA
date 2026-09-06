"""Whole construction trials restore real state even after budget/cancellation expiry."""

import json
from pathlib import Path

import pytest

from kohakuefda.framework import FrameworkError, problem_of
from kohakuefda.framework.control import (
    Budget,
    BudgetExhausted,
    ConfigurationError,
    LocalBudgetExhausted,
    Rejected,
)
from kohakuefda.framework.runtime import Runner
from kohakuefda.model.control import CancelledError
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.scenario import Scenario
from kohakuefda.plan.netlist import build_netlist
from kohakuefda.plan.planner import plan
from kohakuefda.route.pathfinder import NATIVE
from kohakuefda.solvers.regional import Regional

ROOT = Path(__file__).resolve().parents[1]
BACKENDS = ["python"] + (["native"] if NATIVE else [])


@pytest.fixture(scope="module")
def inputs():
    dataset = Dataset.load(ROOT / "data/1.5.3@9764758-3/dataset.json")
    scenario = Scenario.from_toml(ROOT / "tests/fixtures/scenario_valley_battery.toml")
    planned = plan(dataset, scenario)
    problem = problem_of(dataset, build_netlist(dataset, scenario, planned), planned)
    result = Runner(problem, settings={"check_rates": False}).run(
        Regional(shrink_rounds=0)
    )
    return problem, json.loads(result.current.payload)["anchors"]


def construction(inputs, backend, cancelled=None):
    problem, anchors = inputs
    runner = Runner(
        problem,
        settings={"backend": backend, "check_rates": False},
        cancelled=cancelled,
    )
    builder = runner.context.builder()
    for block_id, anchor in anchors:
        assert builder.place(block_id, tuple(anchor)).status == "placed"
    return runner, builder


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize(
    "stop", ["reject", "exception", "cancel", "deadline", "global_work", "local_work"]
)
def test_macro_rollback_restores_more_than_last_action(inputs, backend, stop):
    flag = [False]
    runner, builder = construction(inputs, backend, cancelled=lambda: flag[0])
    before = builder.diagnostic()
    ctx = runner.context
    actions = ctx.budget.work["actions"]
    free = [i for i in ctx.blocks if ctx.blocks[i].constraint == "free"]
    expected = {
        "exception": RuntimeError,
        "cancel": CancelledError,
        "deadline": BudgetExhausted,
        "global_work": BudgetExhausted,
        "local_work": LocalBudgetExhausted,
    }

    def trial():
        with builder.transaction():
            assert builder.withdraw(tuple(free[:2])).status == "removed"
            if stop == "exception":
                raise RuntimeError("interrupt compound edit")
            if stop == "cancel":
                flag[0] = True
                ctx.budget.check()
            if stop == "deadline":
                ctx.budget.seconds = 1e-12
                ctx.budget.check()
            if stop == "global_work":
                ctx.budget.max_actions = ctx.budget.work["actions"]
                builder.withdraw(tuple(free[2:]))
            if stop == "local_work":
                with ctx.budget.limit(actions=0):
                    builder.withdraw(tuple(free[2:]))

    if stop == "reject":
        trial()
    else:
        with pytest.raises(expected[stop]):
            trial()
    flag[0] = False
    ctx.budget.seconds = 0
    ctx.budget.max_actions = 0
    after = builder.diagnostic()
    assert after.payload == before.payload
    assert after.layout_json == before.layout_json
    assert ctx.budget.work["actions"] == actions + 1
    assert ctx.current is None
    with builder.transaction() as next_trial:
        assert next_trial.assess().assessment.routed


@pytest.mark.parametrize("backend", BACKENDS)
def test_assessed_acceptance_keeps_partial_but_never_publishes_it(inputs, backend):
    runner, builder = construction(inputs, backend)
    block_id = next(
        i
        for i in runner.context.blocks
        if runner.context.blocks[i].constraint == "free"
    )
    with builder.transaction() as trial:
        assert builder.withdraw((block_id,)).status == "removed"
        candidate = trial.assess()
        assert not candidate.assessment.complete
        trial.accept()
    assert block_id not in dict(runner.context.anchors)
    assert builder.diagnostic() == candidate
    assert runner.context.current is None
    with pytest.raises(FrameworkError):
        trial.accept()
    with pytest.raises(FrameworkError), trial:
        pass


def test_stale_candidate_and_nested_transaction_cannot_commit(inputs):
    runner, builder = construction(inputs, BACKENDS[-1])
    before = builder.diagnostic()
    with (
        pytest.raises(FrameworkError, match="changed after assessment"),
        builder.transaction() as trial,
    ):
        trial.assess()
        builder.withdraw((runner.context.anchors[0][0],))
        trial.accept()
    assert builder.diagnostic() == before
    with (
        pytest.raises(FrameworkError, match="cannot nest"),
        builder.transaction(),
        builder.transaction(),
    ):
        pass
    with (
        pytest.raises(FrameworkError, match="closed construction"),
        builder.transaction(),
    ):
        builder.finish()
    assert builder.diagnostic() == before


def test_cancel_after_accept_still_rolls_back_whole_trial(inputs):
    flag = [False]
    runner, builder = construction(inputs, BACKENDS[-1], cancelled=lambda: flag[0])
    before = builder.diagnostic()
    with pytest.raises(CancelledError), builder.transaction() as trial:
        builder.withdraw((runner.context.anchors[0][0],))
        trial.assess()
        trial.accept()
        flag[0] = True
    flag[0] = False
    assert builder.diagnostic() == before


@pytest.mark.parametrize("backend", BACKENDS)
def test_partial_group_fault_cannot_be_accepted(backend):
    dataset = Dataset.load(ROOT / "data/1.5.3@9764758-3/dataset.json")
    scenario = Scenario.from_toml(ROOT / "tests/fixtures/scenario_basic.toml")
    planned = plan(dataset, scenario)
    problem = problem_of(dataset, build_netlist(dataset, scenario, planned), planned)
    seed = (
        Runner(problem, settings={"check_rates": False})
        .run(Regional(shrink_rounds=0))
        .current
    )
    runner = Runner(problem, settings={"backend": backend, "check_rates": False})
    builder = runner.context.builder()
    for block_id, anchor in json.loads(seed.payload)["anchors"]:
        if runner.context.blocks[block_id].group == "bus":
            assert builder.place(block_id, tuple(anchor)).status == "placed"
    before = builder.diagnostic()
    section = next(
        i for i, b in runner.context.blocks.items() if b.machine_id == "log_hongs_bus"
    )
    with (
        pytest.raises(Rejected, match="illegal placed geometry"),
        builder.transaction() as trial,
    ):
        assert builder.withdraw((section,)).status == "removed"
        assert runner.context.view.unrouted == ()
        trial.assess()
        trial.accept()
    assert builder.diagnostic() == before


def test_nested_local_allowances_do_not_reset_work_and_global_limit_wins():
    budget = Budget(max_actions=3)
    with budget.limit(actions=5):
        budget.charge("actions")
        with pytest.raises(LocalBudgetExhausted), budget.limit(actions=1):
            budget.charge("actions")
            budget.charge("actions")
        budget.charge("actions")
        with pytest.raises(BudgetExhausted) as error:
            budget.charge("actions")
        assert type(error.value) is BudgetExhausted
    assert budget.work["actions"] == 3
    budget.charge("route_calls")
    assert budget.work["route_calls"] == 1
    with pytest.raises(ConfigurationError), budget.limit(actions=-1):
        pass
