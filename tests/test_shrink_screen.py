"""Greedy screening and duplicate pruning preserve routed outcomes and validation."""

import json
from pathlib import Path

import pytest

from kohakuefda.framework import Action, problem_of, solve
from kohakuefda.framework.actions import rebuild
from kohakuefda.framework.backend import SiteCoverage
from kohakuefda.framework.runtime import Runner
from kohakuefda.model.control import CancelledError
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.scenario import Scenario
from kohakuefda.plan.netlist import build_netlist
from kohakuefda.plan.planner import plan
from kohakuefda.route.pathfinder import NATIVE
from kohakuefda.solvers.baseline import Baseline
from kohakuefda.solvers.baseline.shrink import Shrink

ROOT = Path(__file__).resolve().parents[1]
BACKENDS = [
    "python",
    pytest.param(
        "native", marks=pytest.mark.skipif(not NATIVE, reason="native unavailable")
    ),
]


@pytest.fixture(
    scope="module", params=["scenario_valley_battery", "scenario_gas_xiranite"]
)
def case(request):
    dataset = Dataset.load(ROOT / "data/1.5.3@9764758-3/dataset.json")
    scenario = Scenario.from_toml(ROOT / f"tests/fixtures/{request.param}.toml")
    planned = plan(dataset, scenario)
    problem = problem_of(dataset, build_netlist(dataset, scenario, planned), planned)
    solver = Baseline(spread_attempts=64, shrink_rounds=0)
    result = solve(problem, solver)
    assert result.best_routed is not None
    return problem, result.best_routed, tuple(solver.spread.order)


def replace_machine(ctx):
    for i, anchor in ctx.anchors:
        action = Action("relocate", ((i, anchor),))
        candidate = ctx.attempt(action).candidate
        if candidate is not None:
            ctx.discard(candidate)
            return action
    raise AssertionError("no machine could be replaced at its existing anchor")


@pytest.mark.parametrize("backend", BACKENDS)
def test_screening_and_deduplication_preserve_every_accepted_state(case, backend):
    problem, seed, order = case
    outputs = []
    for fast in (False, True):
        ctx = Runner(problem, settings={"backend": backend}).context
        ctx.import_snapshot(seed)
        accepted = []

        def observe(event, accepted=accepted):
            if event.kind == "accepted":
                accepted.append(json.loads(event.payload_json)["state_id"])

        ctx.observe = observe
        Shrink(ctx, order, 200, screen_candidates=fast, deduplicate=fast).run()
        assert ctx.current.assessment.routed
        ctx.verify()
        outputs.append((ctx.current, accepted))
    assert outputs[0] == outputs[1]


@pytest.mark.parametrize("backend", BACKENDS)
def test_screen_only_rejects_and_receives_actual_immutable_metrics(case, backend):
    problem, seed, _ = case
    ctx = Runner(problem, settings={"backend": backend}).context
    ctx.import_snapshot(seed)
    base, view = ctx.current, ctx.view
    action = replace_machine(ctx)
    measured = []

    def screen(metrics):
        with pytest.raises(TypeError):
            metrics["area"] = 0
        measured.append(dict(metrics))
        return False

    trial = ctx.attempt(action, screen=screen)
    assert trial.status == "screened" and trial.candidate is None
    assert ctx.current is base and ctx.view == view
    checked = ctx.attempt(action).candidate
    assert checked is not None
    assert measured == [dict(checked.snapshot.assessment.metrics)]
    ctx.accept(checked)
    assert ctx.current.assessment.routed


@pytest.mark.parametrize("exception", [RuntimeError, CancelledError])
def test_screen_exception_rolls_back(case, exception):
    problem, seed, _ = case
    ctx = Runner(problem).context
    ctx.import_snapshot(seed)
    original = ctx.view

    def screen(metrics):
        raise exception("screen interrupted")

    with pytest.raises(exception):
        ctx.attempt(
            replace_machine(ctx),
            screen=screen,
        )
    assert ctx.view == original and ctx.current.layout_json == seed.layout_json


def test_approving_screen_cannot_bypass_geometry_checks(case):
    class Coverage:
        name = "test-switchable-cover"
        drop = False

        def __call__(self, site):
            return ([(-10, -10)], []) if self.drop else SiteCoverage()(site)

    problem, seed, _ = case
    cover = Coverage()
    ctx = Runner(problem, coverage=cover).context
    ctx.import_snapshot(seed)
    base, view = ctx.current, ctx.view
    action = replace_machine(ctx)
    cover.drop = True
    trial = ctx.attempt(
        action,
        screen=lambda metrics: True,
    )
    assert trial.status == "hard_conflict" and trial.candidate is None
    assert ctx.current is base and ctx.view == view


def test_duplicate_rebuilds_only_skipped_for_same_revision_and_builtin_edits(case):
    problem, seed, order = case
    ctx = Runner(problem).context
    ctx.import_snapshot(seed)
    shrink = Shrink(ctx, order, 0)
    anchors = dict(ctx.anchors)
    shrink.rebuild(anchors)
    if ctx.current.id != seed.id:
        anchors = dict(ctx.anchors)
        shrink.rebuild(anchors)
    calls = ctx.budget.work["actions"]
    shrink.rebuild(anchors)
    assert ctx.budget.work["actions"] == calls
    assert ctx.budget.work["duplicate_rebuilds"] == 1
    ctx.import_snapshot(ctx.current)
    shrink.rebuild(dict(ctx.anchors))
    assert ctx.budget.work["actions"] == calls + 1
    called = []

    def custom(workspace, action):
        called.append(action)
        rebuild(workspace, action)

    custom_ctx = Runner(problem, actions={"rebuild": custom}).context
    custom_ctx.import_snapshot(seed)
    assert not custom_ctx.repeatable_edits
    custom_shrink = Shrink(custom_ctx, order, 0)
    custom_shrink.rebuild(dict(custom_ctx.anchors))
    custom_shrink.rebuild(dict(custom_ctx.anchors))
    assert len(called) == 2


def test_objectives_without_metric_keys_keep_full_candidate_path(case):
    class Objective:
        name = "test-area-only"

        def key(self, assessment):
            return dict(assessment.metrics)["area"]

    problem, seed, order = case
    ctx = Runner(problem, objective=Objective()).context
    ctx.import_snapshot(seed)
    Shrink(ctx, order, 2).run()
    assert ctx.current.assessment.routed
