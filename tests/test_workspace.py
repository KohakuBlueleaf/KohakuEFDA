"""Boundary relaxation preserves physical rules and cannot publish oversized solutions."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from kohakuefda.framework import problem_of
from kohakuefda.framework.control import (
    BudgetExhausted,
    ConfigurationError,
    FrameworkError,
    LocalBudgetExhausted,
)
from kohakuefda.framework.runtime import Runner
from kohakuefda.framework.workspace import Workspace, boundary_metrics
from kohakuefda.model.control import CancelledError
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.layout import Entry, Layout, Placed, Segment
from kohakuefda.model.scenario import Scenario
from kohakuefda.plan.netlist import build_netlist
from kohakuefda.plan.planner import plan
from kohakuefda.route.pathfinder import NATIVE
from kohakuefda.solvers.local import HillClimbing
from kohakuefda.solvers.outline import OutlineHillClimbing, OutlineSimulatedAnnealing
from kohakuefda.verify.rules.geometry import entries_on_border

ROOT = Path(__file__).resolve().parents[1]
BACKENDS = ["python"] + (["native"] if NATIVE else [])


@pytest.fixture(scope="module")
def dataset():
    return Dataset.load(ROOT / "data/1.5.3@9764758-3/dataset.json")


def problem_for(dataset, name):
    scenario = Scenario.from_toml(ROOT / "tests/fixtures" / f"scenario_{name}.toml")
    planned = plan(dataset, scenario)
    return problem_of(dataset, build_netlist(dataset, scenario, planned), planned)


@pytest.fixture(scope="module")
def problem(dataset):
    return problem_for(dataset, "valley_battery")


@pytest.fixture(scope="module")
def routed(problem):
    return (
        Runner(problem, settings={"check_rates": False})
        .run(HillClimbing(improvement_steps=0))
        .current
    )


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("name", ["valley_battery", "wuling_battery50"])
def test_workspace_changes_only_extent_and_keeps_target_resources(
    dataset, name, backend
):
    problem = problem_for(dataset, name)
    parent = Runner(
        problem,
        settings={"backend": backend, "check_rates": False},
        world={"entry_sides": "NESW"},
    ).context
    before = parent.builder().diagnostic()
    workspace = Workspace(parent, 20)
    child = workspace.context
    assert child.problem is parent.problem
    assert child.blocks == parent.blocks and child.links == parent.links
    assert child.budget is parent.budget
    assert child.area[:2] == parent.area[:2]
    assert child.area[2:] == tuple(v + 20 for v in parent.area[2:])
    assert workspace.backend.site.board.fixed == workspace.backend.target.fixed
    assert workspace.backend.site.board.slots == workspace.backend.target.slots
    assert child.border_anchors() == parent.border_anchors()
    for i, b in child.blocks.items():
        if b.constraint == "slot":
            assert child.slot_anchors(i) == parent.slot_anchors(i)
    assert parent.builder().diagnostic() == before
    assert child._backend.name != parent._backend.name


@pytest.mark.parametrize("backend", BACKENDS)
def test_oversized_partial_is_diagnostic_and_not_publishable(problem, routed, backend):
    parent = Runner(
        problem, settings={"backend": backend, "check_rates": False}
    ).context
    workspace = Workspace(parent, 20)
    child = workspace.context
    block_id = next(
        i for i, b in child.blocks.items() if b.constraint == "free" and not b.group
    )
    _, y0, x1, _ = parent.area
    assert child.builder().place(block_id, (x1 + 2, y0 + 2, 0)).status == "placed"
    snapshot = child.builder().diagnostic()
    workspace.retain(snapshot)
    assert dict(parent.diagnostic.assessment.metrics)["target_overflow"] > 0
    assert not parent.diagnostic.assessment.routed
    assert parent.current is parent.best_routed is parent.best_verified is None
    assert not workspace.publish(snapshot)
    with pytest.raises(ConfigurationError):
        parent.import_snapshot(snapshot)
    assert not parent.anchors
    forged = replace(
        snapshot,
        assessment=replace(
            snapshot.assessment, complete=True, geometry="pass", routing="pass"
        ),
    )
    assert not workspace.publish(forged)


@pytest.mark.parametrize("backend", BACKENDS)
def test_target_publication_reconstructs_original_board_and_does_not_trust_flags(
    problem, routed, backend
):
    parent = Runner(
        problem, settings={"backend": backend, "check_rates": False}
    ).context
    workspace = Workspace(parent, 20)
    child = workspace.context
    for i, anchor in json.loads(routed.payload)["anchors"]:
        assert child.builder().place(i, tuple(anchor)).status == "placed"
    snapshot = child.builder().finish()
    assert workspace.first_routed is not None
    assert parent.best_routed is not None
    assert parent.current.assessment.routed
    layout = Layout.model_validate_json(parent.current.layout_json)
    assert layout.area == parent.area
    assert (layout.width, layout.height) == workspace.backend.target.grid
    assert parent.current.backend == "site-v1"
    assert parent.current.assessment.rates == "not_checked"
    assert snapshot.backend != parent.current.backend
    other = Runner(problem, settings={"backend": backend, "check_rates": False}).context
    other.import_snapshot(parent.current)
    assert other.current.layout_json == parent.current.layout_json


@pytest.mark.parametrize("backend", BACKENDS)
def test_adaptive_growth_retains_actual_partial_routes(problem, routed, backend):
    parent = Runner(
        problem, settings={"backend": backend, "check_rates": False}
    ).context
    first = Workspace(parent, 10)
    anchors = json.loads(routed.payload)["anchors"]
    for i, anchor in anchors[:3]:
        assert first.context.builder().place(i, tuple(anchor)).status == "placed"
    snapshot = first.context.builder().diagnostic()
    before = dict(first.context.anchors)
    larger = Workspace(parent, 20)
    larger.transfer(snapshot)
    assert dict(larger.context.anchors) == before
    assert not larger.context.view.unrouted
    assert larger.context.budget is first.context.budget
    assert parent.best_routed is None
    with pytest.raises(ConfigurationError):
        first.transfer(larger.context.diagnostic)
    assert dict(first.context.anchors) == before


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("stop", ["actions", "local", "cancel"])
def test_workspace_budget_and_rollback_are_shared(problem, backend, stop):
    flag = [False]
    parent = Runner(
        problem,
        settings={"backend": backend, "check_rates": False},
        cancelled=lambda: flag[0],
    ).context
    workspace = Workspace(parent, 20)
    child = workspace.context
    builder = child.builder()
    before = builder.diagnostic()
    block_id = next(
        i for i, b in child.blocks.items() if b.constraint == "free" and not b.group
    )
    expected = {
        "actions": BudgetExhausted,
        "local": LocalBudgetExhausted,
        "cancel": CancelledError,
    }
    with pytest.raises(expected[stop]), builder.transaction():
        x0, y0, _, _ = child.area
        assert builder.place(block_id, (x0 + 10, y0 + 10, 0)).status == "placed"
        if stop == "actions":
            parent.budget.max_actions = parent.budget.work["actions"]
        elif stop == "cancel":
            flag[0] = True
        with child.budget.limit(actions=0):
            builder.withdraw((block_id,))
    flag[0] = False
    parent.budget.max_actions = 0
    assert builder.diagnostic() == before
    assert parent.best_routed is None
    assert parent.budget.work["actions"] == 1


def test_boundary_metric_exempts_plain_ring_pipes_not_machines_or_belts(dataset):
    problem = problem_for(dataset, "wuling_battery50")
    parent = Runner(problem).context
    workspace = Workspace(parent, 20)
    target = workspace.backend.target
    _, y0, x1, _ = target.area
    layout = Layout(
        dataset_version=dataset.version.id,
        basement=Scenario.model_validate(
            json.loads(problem.netlist_json)["scenario"]
        ).basement,
        width=workspace.context.view.grid[0],
        height=workspace.context.view.grid[1],
        area=workspace.context.area,
    )
    layout.segments = [Segment(id="outside", kind="pipe", cells=[(x1, y0)])]
    assert boundary_metrics(dataset, layout, target)["target_overflow"] == 0
    layout.segments[0].kind = "belt"
    assert boundary_metrics(dataset, layout, target)["target_overflow"] == 1
    layout.segments[0].kind = "pipe"
    layout.segments[0].cells = [(target.grid[0], y0)]
    assert boundary_metrics(dataset, layout, target)["target_overflow"] == 1
    layout.segments = []
    machine = next(b.machine_id for b in parent.blocks.values() if b.kind == "recipe")
    layout.machines = [Placed(id="outside", machine_id=machine, x=x1, y=y0)]
    assert boundary_metrics(dataset, layout, target)["target_overflow"] > 0
    layout.machines = []
    layout.entries = [
        Entry(id="entry", item_id="water", rate=1, x=x1 - 1, y=y0 + 2, edge="E")
    ]
    assert entries_on_border(layout)
    assert not entries_on_border(layout, target.area)
    with pytest.raises(FrameworkError):
        Workspace(workspace.context, 10)


@pytest.mark.parametrize("backend", BACKENDS)
def test_outline_solver_can_publish_small_problem_and_zero_temperature_matches(
    problem, backend
):
    results = []
    for solver in (
        OutlineHillClimbing(improvement_steps=30),
        OutlineSimulatedAnnealing(
            improvement_steps=30,
            construction_temperature=0,
            construction_final_temperature=0,
            layout_temperature=0,
            layout_final_temperature=0,
        ),
    ):
        runner = Runner(problem, settings={"backend": backend, "check_rates": False})
        results.append(runner.run(solver))
    assert results[0].status == results[1].status == "completed"
    assert results[0].best_routed == results[1].best_routed
    assert results[0].best_routed.assessment.routed


@pytest.mark.parametrize(
    "options",
    [
        {"workspace_extra": 0},
        {"workspace_extra": 300},
        {"workspace_max_extra": 10},
        {"workspace_growth": 0},
        {"workspace_steps": 0},
        {"outline_radius": 0},
    ],
)
def test_workspace_settings_validate_before_search(options):
    with pytest.raises(ConfigurationError):
        OutlineHillClimbing(**options)
