"""Public solver/action contracts over real geometry, routing and verification."""

import json
import subprocess
import sys
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from kohakuefda.framework import Action, FrameworkError, Scope, problem_of, solve
from kohakuefda.framework.checkpoint import load_snapshot, save_snapshot
from kohakuefda.framework.control import BudgetExhausted, ConfigurationError
from kohakuefda.framework.runtime import Runner
from kohakuefda.framework.scopes import component
from kohakuefda.model.control import CancelledError
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.layout import Layout
from kohakuefda.model.scenario import Scenario
from kohakuefda.plan.machines import recipe_cell
from kohakuefda.plan.netlist import build_netlist
from kohakuefda.plan.planner import plan
from kohakuefda.route.pathfinder import NATIVE, RouteGrid
from kohakuefda.solvers.baseline import Baseline

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def problem():
    dataset = Dataset.load(ROOT / "data/1.5.3@9764758-3/dataset.json")
    scenario = Scenario.from_toml(ROOT / "tests/fixtures/scenario_valley_battery.toml")
    planned = plan(dataset, scenario)
    return problem_of(dataset, build_netlist(dataset, scenario, planned), planned)


@pytest.fixture(scope="module")
def seed(problem):
    result = solve(problem, Baseline(shrink_rounds=0))
    assert result.current.assessment.verified
    return result.current


class Identity:
    name = "test-identity"
    capabilities = frozenset()

    def solve(self, context):
        return "completed"


class Rewire:
    name = "test-rewire"
    capabilities = frozenset({"reroute"})

    def solve(self, context):
        action = Action("reroute", routes=tuple(link.id for link in context.links))
        result = context.attempt(action)
        if result.candidate:
            context.accept(result.candidate)
        return "completed"


def move_action(ctx):
    i = next(i for i, _ in ctx.view.anchors if ctx.blocks[i].constraint == "free")
    x, y, rotation = dict(ctx.view.anchors)[i]
    return Action("relocate", ((i, (x, y + 1, rotation)),))


@pytest.mark.parametrize(
    "backend",
    [
        "python",
        pytest.param(
            "native",
            marks=pytest.mark.skipif(not NATIVE, reason="native grid unavailable"),
        ),
    ],
)
def test_snapshot_roundtrip_and_real_second_solver(problem, seed, tmp_path, backend):
    path = tmp_path / "checkpoint.json"
    save_snapshot(seed, path)
    restored = load_snapshot(path)
    assert restored == seed
    result = solve(problem, Identity(), seed=restored, settings={"backend": backend})
    assert result.current.layout_json == seed.layout_json
    assert result.current.assessment.verified
    again = solve(problem, Rewire(), seed=restored, settings={"backend": backend})
    assert again.current.assessment.routed
    assert Layout.model_validate_json(again.current.layout_json).machines
    with pytest.raises(FrozenInstanceError):
        restored.problem_id = "other"


@pytest.mark.parametrize(
    "backend",
    [
        "python",
        pytest.param(
            "native",
            marks=pytest.mark.skipif(not NATIVE, reason="native grid unavailable"),
        ),
    ],
)
def test_transaction_candidate_rejection_stale_and_scope(problem, seed, backend):
    runner = Runner(problem, settings={"backend": backend})
    ctx = runner.context
    ctx.import_snapshot(seed)
    original = ctx.current
    view = ctx.view
    action = move_action(ctx)
    candidate = ctx.attempt(action).candidate
    assert candidate is not None
    assert ctx.current == original and ctx.view == view
    scoped = replace(
        action, scope=Scope(frozenset(i for i, _ in action.anchors), frozenset())
    )
    assert ctx.attempt(scoped).status == "scope_required"
    assert ctx.view == view
    bad = replace(action, anchors=((action.anchors[0][0], (-5, -5, 0)),))
    assert ctx.attempt(bad).candidate is None
    assert ctx.current == original and ctx.view == view
    another = ctx.attempt(action).candidate
    ctx.accept(candidate)
    assert ctx.current == candidate.snapshot
    assert ctx.attempt(action, base_revision=view.revision).status == "stale"
    with pytest.raises(FrameworkError, match="stale"):
        ctx.accept(another)
    with pytest.raises(FrameworkError):
        ctx.accept(replace(candidate, base_revision=ctx.revision))


@pytest.mark.parametrize("exception", [RuntimeError, CancelledError, BudgetExhausted])
def test_custom_action_exception_rolls_back_everything(problem, seed, exception):
    held = []

    def action(workspace, spec):
        held.append(workspace)
        workspace.remove(spec.anchors[0][0])
        raise exception("test exit")

    ctx = Runner(problem, actions={"explode": action}).context
    ctx.import_snapshot(seed)
    before = ctx.view
    spec = replace(move_action(ctx), name="explode")
    with pytest.raises(exception):
        ctx.attempt(spec)
    assert ctx.view == before and ctx.current.layout_json == seed.layout_json
    with pytest.raises(FrameworkError, match="closed"):
        held[0].remove(spec.anchors[0][0])
    candidate = ctx.attempt(replace(spec, name="relocate")).candidate
    assert candidate is not None
    ctx.accept(candidate)
    assert ctx.current.assessment.routed


def test_limits_and_cancel_return_last_published_state(problem, seed):
    class Limited:
        name = "limited"
        capabilities = frozenset({"relocate"})

        def solve(self, ctx):
            for _ in range(2):
                trial = ctx.attempt(move_action(ctx))
                if trial.candidate:
                    ctx.accept(trial.candidate)
            return "completed"

    result = solve(problem, Limited(), seed=seed, settings={"max_actions": 1})
    assert result.status == "budget_exhausted" and result.current.assessment.routed
    assert dict(result.work)["actions"] == 1
    stopped = solve(problem, Identity(), cancelled=lambda: True)
    assert stopped.status == "cancelled" and stopped.current is None


def test_observer_and_hierarchy_are_read_only(problem, seed):
    def watch(event):
        json.loads(event.payload_json)
        raise RuntimeError("disconnected viewer")

    a = solve(problem, Rewire(), seed=seed, observe=watch)
    b = solve(problem, Rewire(), seed=seed)
    assert a.current.layout_json == b.current.layout_json
    ctx = Runner(problem).context
    ctx.import_snapshot(seed)
    i = move_action(ctx).anchors[0][0]
    part = component(ctx, frozenset({i}))
    assert part.boundary and part.occupied
    assert part.scope().machines == frozenset({i})


def test_checkpoint_identity_and_evidence_cannot_be_forged(problem, seed):
    ctx = Runner(problem).context
    with pytest.raises(ConfigurationError):
        ctx.import_snapshot(replace(seed, problem_id="wrong"))
    with pytest.raises(ConfigurationError):
        ctx.import_snapshot(replace(seed, payload="{}"))
    assert ctx.view.missing and ctx.current is None
    ctx.import_snapshot(seed)
    assert ctx.current.assessment.rates == "not_checked"
    ctx.verify()
    assert ctx.current.assessment.verified


def test_port_domains_do_not_depend_on_ingredient_order():
    dataset = Dataset.load(ROOT / "data/1.5.3@9764758-3/dataset.json")
    recipe = dataset.recipes["tools_proc_battery_3_1"]
    forward = recipe_cell(dataset, "f", recipe)
    reverse = recipe_cell(
        dataset,
        "r",
        recipe.model_copy(update={"inputs": list(reversed(recipe.inputs))}),
    )

    def domains(cell):
        return {p.id: {o.index for o in p.alternatives} for p in cell.pins}

    assert domains(forward) == domains(reverse)
    liquid = dataset.recipes["xiranite_oven_xiranite_powder_2"]
    cell = recipe_cell(dataset, "p", liquid)
    for pin in cell.pins:
        if pin.kind == "pipe" and pin.direction == "out":
            assert {o.index for o in pin.alternatives} == set(
                dataset.output_ports(liquid, pin.item_id)
            )


def test_framework_imports_no_concrete_solver():
    code = "import kohakuefda.framework, sys; assert not any(n.startswith('kohakuefda.solvers') for n in sys.modules)"
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_parallel_construction_and_import(problem):
    a = solve(
        problem,
        Baseline(spread_attempts=8, spread_slice=4, shrink_rounds=0),
        settings={"workers": 2},
    )
    b = solve(
        problem,
        Baseline(spread_attempts=8, spread_slice=4, shrink_rounds=0),
        settings={"workers": 2},
    )
    assert (
        a.current.assessment.verified and a.current.layout_json == b.current.layout_json
    )


@pytest.mark.skipif(not NATIVE, reason="native grid unavailable")
def test_native_snapshot_rejects_foreign_dimensions():
    small = RouteGrid(4, 4, [set(), set()])
    large = RouteGrid(6, 6, [set(), set()])
    with pytest.raises(ValueError, match="dimensions"):
        large.load(small.save())
    assert large.width == 6 and large.height == 6


def test_routing_addon_builder_exception_and_expired_builder(problem, seed):
    class ExplodingRouter:
        name = "exploding-test-router"

        def __call__(self, site, required):
            raise RuntimeError("routing interrupted")

    ctx = Runner(problem, routing=ExplodingRouter()).context
    builder = ctx.builder()
    before = ctx.view
    machine, anchor = json.loads(seed.payload)["anchors"][0]
    with pytest.raises(RuntimeError, match="routing interrupted"):
        builder.place(machine, tuple(anchor))
    assert ctx.view == before
    ctx.import_snapshot(seed)
    with pytest.raises(FrameworkError, match="closed"):
        builder.reset()
    assert ctx.current.assessment.routed


def test_offering_a_candidate_does_not_change_current(problem, seed):
    ctx = Runner(problem).context
    ctx.import_snapshot(seed)
    before = ctx.current
    trial = ctx.attempt(move_action(ctx))
    assert trial.candidate is not None
    ctx.consider(trial.candidate.snapshot)
    assert ctx.current is before
    ctx.discard(trial.candidate)
    with pytest.raises(FrameworkError):
        ctx.consider(replace(seed))
