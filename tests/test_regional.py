"""Regional strategy and its public construction/endpoint contracts over real routing."""

import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from kohakuefda.framework import FrameworkError, problem_of
from kohakuefda.framework.control import BudgetExhausted, ConfigurationError
from kohakuefda.framework.runtime import Runner
from kohakuefda.model.control import CancelledError
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.scenario import Scenario
from kohakuefda.plan.netlist import build_netlist
from kohakuefda.plan.planner import plan
from kohakuefda.route.pathfinder import NATIVE
from kohakuefda.solvers import SOLVERS
from kohakuefda.solvers.regional import Regional

ROOT = Path(__file__).resolve().parents[1]
BACKENDS = ["python"] + (["native"] if NATIVE else [])


@pytest.fixture(scope="module")
def problem():
    dataset = Dataset.load(ROOT / "data/1.5.3@9764758-3/dataset.json")
    scenario = Scenario.from_toml(ROOT / "tests/fixtures/scenario_valley_battery.toml")
    planned = plan(dataset, scenario)
    return problem_of(dataset, build_netlist(dataset, scenario, planned), planned)


@pytest.fixture(scope="module")
def constructed(problem):
    events = []
    result = Runner(
        problem, settings={"check_rates": False}, observe=events.append
    ).run(Regional(shrink_rounds=0))
    assert result.best_routed is not None
    assert result.best_routed.assessment.rates == "not_checked"
    assert len([event for event in events if event.kind == "constructed"]) == 1
    return result.best_routed


def replay(problem, snapshot, backend, routing=None):
    runner = Runner(
        problem, settings={"backend": backend, "check_rates": False}, routing=routing
    )
    builder = runner.context.builder()
    for block_id, anchor in json.loads(snapshot.payload)["anchors"]:
        assert builder.place(block_id, tuple(anchor)).status == "placed"
    return runner, builder


@pytest.mark.parametrize("backend", BACKENDS)
def test_regional_reproducible_complete_and_cataloged(problem, backend):
    snapshots = []
    for _ in range(2):
        result = Runner(
            problem, settings={"backend": backend, "check_rates": False}
        ).run(SOLVERS.get("regional").build({"shrink_rounds": 0}))
        assert result.status == "completed"
        assert result.current.assessment.routed
        snapshots.append(result.current)
    assert snapshots[0].layout_json == snapshots[1].layout_json
    assert snapshots[0].payload == snapshots[1].payload


@pytest.mark.parametrize("backend", BACKENDS)
def test_withdraw_and_restore_preserve_routed_partial_contract(
    problem, constructed, backend
):
    runner, builder = replay(problem, constructed, backend)
    ctx = runner.context
    before = builder.diagnostic()
    mark = builder.mark()
    block_id = next(i for i, _ in ctx.anchors if ctx.blocks[i].constraint == "free")
    assert builder.withdraw((block_id,)).status == "removed"
    assert block_id not in dict(ctx.anchors)
    assert ctx.view.unrouted == ()
    assert ctx.current is None
    assert ctx.best_routed is None
    assert not builder.diagnostic().assessment.complete
    builder.restore(mark)
    assert builder.diagnostic().layout_json == before.layout_json
    assert builder.withdraw(("not-a-block",)).status == "hard_conflict"
    assert builder.diagnostic().layout_json == before.layout_json
    builder.finish()
    assert ctx.current.assessment.routed
    with pytest.raises(FrameworkError, match="closed"):
        builder.withdraw((block_id,))


class RepairFailure:
    name = "test-repair-failure"

    def __init__(self, exception):
        self.exception = exception
        self.fail = False

    def __call__(self, site, required):
        if not self.fail:
            return site.wire_up(required)
        if self.exception:
            raise self.exception("repair interrupted")
        return False


@pytest.mark.parametrize(
    "exception", [None, RuntimeError, CancelledError, BudgetExhausted]
)
@pytest.mark.parametrize("backend", BACKENDS)
def test_withdraw_failure_or_exception_rolls_back(
    problem, constructed, backend, exception
):
    routing = RepairFailure(exception)
    runner, builder = replay(problem, constructed, backend, routing)
    before = builder.diagnostic()
    revision = runner.context.revision
    routing.fail = True
    block_id = runner.context.anchors[0][0]
    if exception:
        with pytest.raises(exception):
            builder.withdraw((block_id,))
    else:
        assert builder.withdraw((block_id,)).status != "removed"
    assert builder.diagnostic().layout_json == before.layout_json
    assert runner.context.revision == revision


@pytest.mark.parametrize("backend", BACKENDS)
def test_connection_targets_are_immutable_nonmutating_queries(
    problem, constructed, backend
):
    runner, builder = replay(problem, constructed, backend)
    before = builder.diagnostic()
    trees = dict(runner.backend.site.router.trees)
    for block_id in runner.context.blocks:
        targets = runner.context.connection_targets(block_id)
        assert all(
            t.lane_id in {p.id for p in runner.context.blocks[block_id].lanes}
            for t in targets
        )
        if targets:
            with pytest.raises(FrozenInstanceError):
                targets[0].lane_id = "changed"
    assert runner.backend.site.router.trees == trees
    assert builder.diagnostic().layout_json == before.layout_json


@pytest.mark.parametrize(
    "options",
    [
        {"attempts": 0},
        {"gap_cycle": 0},
        {"radius_cycle": 0},
        {"repair_threshold": 2},
        {"depot_step": 20},
    ],
)
def test_regional_rejects_invalid_policy_settings(options):
    with pytest.raises(ConfigurationError):
        Regional(**options)


@pytest.mark.parametrize("backend", BACKENDS)
def test_endpoint_query_does_not_insert_empty_trees(problem, constructed, backend):
    runner = Runner(problem, settings={"backend": backend, "check_rates": False})
    ctx = runner.context
    builder = ctx.builder()
    first, anchor = json.loads(constructed.payload)["anchors"][0]
    assert builder.place(first, tuple(anchor)).status == "placed"
    before = dict(runner.backend.site.router.trees)
    targets = [t for block_id in ctx.blocks for t in ctx.connection_targets(block_id)]
    assert targets
    assert all(t.cells for t in targets)
    assert runner.backend.site.router.trees == before


def test_regional_honors_work_budget_without_publishing_partial(problem):
    result = Runner(problem, settings={"max_actions": 1, "check_rates": False}).run(
        Regional()
    )
    assert result.status == "budget_exhausted"
    assert result.best_routed is None
    assert result.best_verified is None
    assert dict(result.work)["actions"] == 1
