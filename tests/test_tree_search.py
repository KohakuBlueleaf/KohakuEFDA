"""Structural mutations, coupled realization and genotype/phenotype rollback."""

import json
import random
from dataclasses import asdict, replace
from itertools import combinations, pairwise
from pathlib import Path

import pytest

from kohakuefda.framework import problem_of
from kohakuefda.framework.control import (
    BudgetExhausted,
    ConfigurationError,
    LocalBudgetExhausted,
)
from kohakuefda.framework.runtime import Runner
from kohakuefda.model.control import CancelledError
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.scenario import Scenario
from kohakuefda.plan.netlist import build_netlist
from kohakuefda.plan.planner import plan
from kohakuefda.route.pathfinder import NATIVE
from kohakuefda.solvers.local import (
    HillClimbing,
    TreeHillClimbing,
    TreeSimulatedAnnealing,
)
from kohakuefda.solvers.local.structural import TreeLayout, TreeState, TreeTrajectory
from kohakuefda.solvers.local.tree import FloorTree, initial_tree

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


def problem_for(dataset, name):
    scenario = Scenario.from_toml(ROOT / "tests/fixtures" / f"scenario_{name}.toml")
    planned = plan(dataset, scenario)
    return problem_of(dataset, build_netlist(dataset, scenario, planned), planned)


@pytest.fixture(scope="module")
def problem(dataset):
    return problem_for(dataset, "valley_battery")


def tree_for(problem):
    context = Runner(problem).context
    blocks = {
        i: b
        for i, b in context.blocks.items()
        if b.constraint == "free" and not b.group
    }
    return initial_tree(blocks, tuple(blocks), context.area, 2), blocks, context.area


def test_tree_mutations_preserve_valid_topology_and_make_global_moves(problem):
    tree, blocks, area = tree_for(problem)
    original = tree.id
    rng = random.Random(4)
    maximum = 0
    for _ in range(100):
        before = tree.pack(blocks, area)
        _, candidate = tree.mutate(rng, 4)
        assert set(candidate.traversal()) == set(range(len(tree.labels)))
        assert sorted(candidate.labels) == sorted(tree.labels)
        assert FloorTree.from_json(json.dumps(asdict(candidate))) == candidate
        after = candidate.pack(blocks, area)
        maximum = max(maximum, sum(before[i] != after[i] for i in before))
        rectangles = []
        for i, (x, y, r) in after.items():
            b = blocks[i]
            w, h = (b.width, b.height) if r % 180 == 0 else (b.height, b.width)
            rectangles.append((x, y, x + w, y + h))
        for a, b in combinations(rectangles, 2):
            assert a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1]
        tree = candidate
    assert tree.id != original
    assert maximum >= len(blocks) // 2


@pytest.mark.parametrize(
    "change",
    [
        {"left": (0, -1)},
        {"right": (1, -1), "left": (1, -1)},
        {"left": (-1, -1)},
        {"rotations": (45, 0)},
        {"gaps": (0, 1)},
        {"labels": ("a", "a")},
        {"left": (3, -1)},
        {"root": -1},
    ],
)
def test_tree_rejects_invalid_serialized_topology(change):
    tree = FloorTree(("a", "b"), (0, 0), (1, -1), (-1, -1), (1, 1))
    with pytest.raises(ConfigurationError):
        replace(tree, **change)


def test_empty_tree_and_overflow_are_explicit(problem):
    assert FloorTree((), (), (), (), ()).traversal() == ()
    tree, blocks, _ = tree_for(problem)
    anchors = tree.pack(blocks, (0, 0, 1, 1))
    assert len(anchors) == len(blocks)
    assert any(x >= 1 or y >= 1 for x, y, r in anchors.values())


def run(problem, solver, backend):
    events = []
    runner = Runner(
        problem,
        settings={"backend": backend, "check_rates": False},
        observe=events.append,
    )
    result = runner.run(solver)
    rows = [json.loads(e.payload_json) for e in events if e.kind == "transition"]
    return runner, result, rows


@pytest.mark.parametrize("backend", BACKENDS)
def test_tree_zero_temperature_equivalence_and_rejected_genotype_rollback(
    problem, backend
):
    options = {"tree_every": 1, "improvement_steps": 40, "tree_improvement": True}
    hc_runner, hc, hc_rows = run(problem, TreeHillClimbing(**options), backend)
    sa_runner, sa, sa_rows = run(
        problem, TreeSimulatedAnnealing(**options, **ZERO), backend
    )
    assert hc.status == sa.status == "completed"
    assert hc.best_routed == sa.best_routed
    assert hc.current.assessment.routed
    assert hc_rows and any(row["operator"].startswith("tree.") for row in hc_rows)
    for rows in (hc_rows, sa_rows):
        for row in rows:
            assert row["tree_next"] == (
                row["tree_candidate"] if row["accepted"] else row["tree_parent"]
            )
        for before, after in pairwise(rows):
            assert before["tree_next"] == after["tree_parent"]
    assert [(r["candidate"], r["accepted"]) for r in hc_rows] == [
        (r["candidate"], r["accepted"]) for r in sa_rows
    ]
    assert "local.tree" not in hc_runner.context.actions
    assert "local.tree" not in sa_runner.context.actions


@pytest.mark.parametrize("backend", BACKENDS)
def test_tree_construction_keeps_physical_and_structural_current_together(
    dataset, backend
):
    problem = problem_for(dataset, "wuling_battery50")
    runner, result, rows = run(
        problem,
        TreeHillClimbing(construction_steps=6, improvement_steps=0, tree_every=1),
        backend,
    )
    assert result.status == "no_solution_found"
    assert rows
    assert any(row["tree_changed_targets"] > 10 for row in rows)
    for row in rows:
        assert row["tree_next"] == (
            row["tree_candidate"] if row["accepted"] else row["tree_parent"]
        )
    for before, after in pairwise(rows):
        assert before["tree_next"] == after["tree_parent"]
        assert before["next_parent"] == after["parent"]
    assert runner.context.diagnostic is not None


@pytest.mark.parametrize(
    "option",
    [
        {"tree_every": 0},
        {"tree_gap": 0},
        {"tree_gap": 5},
        {"tree_candidates": 0},
        {"tree_pull": -1},
        {"tree_clearance": -1},
    ],
)
def test_invalid_tree_options_fail_before_search(option):
    with pytest.raises(ConfigurationError):
        TreeHillClimbing(**option)


@pytest.fixture(scope="module")
def routed(problem):
    return (
        Runner(problem, settings={"check_rates": False})
        .run(HillClimbing(improvement_steps=0))
        .current
    )


@pytest.mark.parametrize("text", ["[]", "null", "{}", "{", '{"labels":null}'])
def test_malformed_tree_has_typed_error(text):
    with pytest.raises(ConfigurationError):
        FloorTree.from_json(text)


@pytest.mark.parametrize("backend", BACKENDS)
def test_relative_targets_follow_retained_physical_displacement(
    problem, routed, backend
):
    ctx = Runner(problem, settings={"backend": backend, "check_rates": False}).context
    ctx.import_snapshot(routed)
    state = TreeState(ctx, TreeHillClimbing().settings)
    original = state.current
    old = original.pack(ctx.blocks, ctx.area)
    for _ in range(12):
        state.begin()
        new = state.candidate.pack(ctx.blocks, ctx.area)
        for i in state.changed:
            x, y, r = state.before[i]
            ox, oy, rotation = old[i]
            nx, ny, turned = new[i]
            assert state.hints[i] == (
                x + nx - ox,
                y + ny - oy,
                (r + turned - rotation) % 360,
            )
        assert state.current == original
    state.accept()
    assert state.current == state.candidate


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("stop", ["local", "global", "cancel"])
def test_interrupted_tree_trial_rolls_back_physical_and_structural_state(
    problem, routed, backend, stop
):
    flag = [False]
    ctx = Runner(
        problem,
        settings={"backend": backend, "check_rates": False},
        cancelled=lambda: flag[0],
    ).context
    builder = ctx.builder()
    for i, anchor in json.loads(routed.payload)["anchors"]:
        assert builder.place(i, tuple(anchor)).status == "placed"
    before = builder.diagnostic()
    trajectory = TreeTrajectory(ctx, TreeHillClimbing(tree_every=1).settings, "hc")
    state = trajectory.tree_state
    original = state.current
    for _ in range(20):
        state.begin()
        if state.removed():
            break
    assert state.removed()
    errors = {
        "local": LocalBudgetExhausted,
        "global": BudgetExhausted,
        "cancel": CancelledError,
    }
    with pytest.raises(errors[stop]), builder.transaction():
        assert builder.withdraw(state.removed()).status == "removed"
        if stop == "cancel":
            flag[0] = True
        if stop == "global":
            ctx.budget.max_actions = ctx.budget.work["actions"]
        with ctx.budget.limit(actions=0):
            state.decoder.run(
                state.candidate,
                lambda i, a: builder.place(i, a).status == "placed",
                state.hints,
            )
    flag[0] = False
    ctx.budget.max_actions = 0
    assert builder.diagnostic() == before
    assert state.current == original
    state.begin()
    assert state.parent == original


@pytest.mark.parametrize("backend", BACKENDS)
def test_serialized_tree_action_is_independent_of_later_proposal(
    problem, routed, backend
):
    ctx = Runner(problem, settings={"backend": backend, "check_rates": False}).context
    ctx.import_snapshot(routed)
    options = TreeHillClimbing(tree_every=1, tree_improvement=True).settings
    state = TreeState(ctx, options)
    moves = TreeLayout(ctx, options, state)
    try:
        for _ in range(20):
            _, action = moves.propose()
            if action is not None:
                break
        assert action is not None
        before = ctx.current
        first = ctx.attempt(action)
        for _ in range(5):
            state.begin()
        second = ctx.attempt(action)
        assert first.status == second.status
        assert (first.candidate.snapshot if first.candidate else None) == (
            second.candidate.snapshot if second.candidate else None
        )
        assert ctx.current == before
        for result in (first, second):
            if result.candidate:
                ctx.discard(result.candidate)
    finally:
        moves.close()
    assert "local.tree" not in ctx.actions


def test_structurally_distinct_physical_duplicates_are_neutral(problem, routed):
    ctx = Runner(problem, settings={"check_rates": False}).context
    ctx.import_snapshot(routed)
    trajectory = TreeTrajectory(ctx, TreeHillClimbing().settings, "hc")
    state = trajectory.tree_state
    while state.candidate == state.parent:
        state.begin()
    delta, decision, outcome = trajectory.choose(routed, routed, "layout", 0)
    assert delta == 0 and decision.accepted and outcome == "accepted"
    state.accept()
    state.begin(False)
    assert trajectory.choose(routed, routed, "layout", 0)[2] == "duplicate"


@pytest.mark.parametrize("backend", BACKENDS)
def test_default_tree_layout_phase_preserves_original_improvement_trajectory(
    problem, routed, backend
):
    results = []
    for solver in (
        HillClimbing(improvement_steps=50),
        TreeHillClimbing(improvement_steps=50),
    ):
        runner = Runner(problem, settings={"backend": backend, "check_rates": False})
        results.append(runner.run(solver, seed=routed))
    assert results[0].current == results[1].current
    assert results[0].best_routed == results[1].best_routed
    assert results[0].work == results[1].work
