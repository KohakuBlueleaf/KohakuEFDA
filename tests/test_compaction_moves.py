"""Area-directed HC/SA moves preserve physical legality and area-first ordering."""

import json
import random
import subprocess
import sys
from dataclasses import asdict
from itertools import pairwise
from pathlib import Path

import pytest

from kohakuefda.framework import problem_of
from kohakuefda.framework.runtime import Runner
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.scenario import Scenario
from kohakuefda.plan.netlist import build_netlist
from kohakuefda.plan.planner import plan
from kohakuefda.route.pathfinder import NATIVE
from kohakuefda.solvers.local import DEFAULTS, HillClimbing, SimulatedAnnealing
from kohakuefda.solvers.local.compact import CompactionMoves
from kohakuefda.solvers.local.moves import LayoutMoves
from kohakuefda.solvers.local.policy import layout_delta

ROOT = Path(__file__).resolve().parents[1]
BACKENDS = ["python"] + (["native"] if NATIVE else [])


@pytest.fixture(scope="module")
def inputs():
    dataset = Dataset.load(ROOT / "data/1.5.3@9764758-3/dataset.json")
    scenario = Scenario.from_toml(ROOT / "tests/fixtures/scenario_valley_battery.toml")
    planned = plan(dataset, scenario)
    netlist = build_netlist(dataset, scenario, planned)
    problem = problem_of(dataset, netlist, planned)
    result = Runner(problem, settings={"check_rates": False}).run(
        HillClimbing(improvement_steps=0)
    )
    assert result.current.assessment.routed
    return problem, result.current, planned, netlist


@pytest.mark.parametrize("backend", BACKENDS)
def test_cut_candidates_are_unique_and_coupled(inputs, backend):
    problem, seed, _, _ = inputs
    ctx = Runner(problem, settings={"backend": backend, "check_rates": False}).context
    ctx.import_snapshot(seed)
    proposals = CompactionMoves(ctx, DEFAULTS, random.Random(0))
    actions = []
    while (action := proposals.cut()) is not None:
        actions.append(action)
    assert actions
    assert len({action.anchors for action in actions}) == len(actions)
    accepted = False
    for action in actions:
        before = ctx.current
        assert all(
            ctx.blocks[i].constraint not in ("slot", "edge") for i, _ in action.anchors
        )
        assert all(a != dict(ctx.anchors)[i] for i, a in action.anchors)
        result = ctx.attempt(action)
        assert ctx.current == before
        if result.candidate:
            assert result.candidate.snapshot.assessment.routed
            ctx.accept(result.candidate)
            accepted = True
            break
    assert accepted
    assert proposals.signature != ctx.current.id
    proposals.cut()
    assert proposals.signature == ctx.current.id


@pytest.mark.parametrize("backend", BACKENDS)
def test_pull_uses_legal_domains_and_rolls_back_failed_routes(inputs, backend):
    problem, seed, _, _ = inputs
    ctx = Runner(problem, settings={"backend": backend, "check_rates": False}).context
    ctx.import_snapshot(seed)
    proposals = CompactionMoves(ctx, DEFAULTS, random.Random(0))
    slots = 0
    for _ in range(50):
        action = proposals.pull()
        if action is None:
            continue
        block_id, anchor = action.anchors[0]
        if ctx.blocks[block_id].constraint == "slot":
            slots += 1
            assert anchor in ctx.slot_anchors(block_id)
        if ctx.blocks[block_id].constraint == "edge":
            assert anchor in ctx.border_anchors()
        before = ctx.current
        result = ctx.attempt(action)
        assert ctx.current == before
        if result.candidate:
            assert result.candidate.snapshot.assessment.routed
            ctx.discard(result.candidate)
    assert slots > 0


@pytest.mark.parametrize("solver", [HillClimbing, SimulatedAnnealing])
@pytest.mark.parametrize("backend", BACKENDS)
def test_compaction_reduces_real_area_with_valid_current_lineage(
    inputs, solver, backend
):
    problem, seed, _, _ = inputs
    events = []
    result = Runner(
        problem,
        settings={"backend": backend, "check_rates": False},
        observe=events.append,
    ).run(solver(improvement_steps=600), seed=seed)
    assert result.best_routed.assessment.routed
    assert result.current.assessment.routed
    assert (
        dict(result.best_routed.assessment.metrics)["area"]
        < dict(seed.assessment.metrics)["area"]
    )
    rows = [json.loads(e.payload_json) for e in events if e.kind == "transition"]
    assert any(row["operator"] == "cut" for row in rows)
    assert any(row["operator"] == "pull" for row in rows)
    for before, after in pairwise(rows):
        assert before["next_parent"] == after["parent"]
    if solver is HillClimbing:
        assert all(row["area_delta"] <= 0 for row in rows if row["accepted"])
        assert all(
            row["wire_delta"] <= 0
            for row in rows
            if row["accepted"] and row["area_delta"] == 0
        )


def test_tiebreak_never_outweighs_a_single_area_cell():
    small_long = {"area": 1000.0, "wire_path_cells": 1e12}
    large_short = {"area": 1001.0, "wire_path_cells": 0.0}
    for coefficient in (0.0, 0.5, 0.999):
        assert layout_delta(small_long, large_short, 4900, coefficient) > 0
        assert layout_delta(large_short, small_long, 4900, coefficient) < 0
    short = {**small_long, "wire_path_cells": 100.0}
    assert layout_delta(small_long, short, 4900, 0.5) < 0
    assert layout_delta(small_long, short, 4900, 0.0) == 0
    assert layout_delta(short, short, 4900, 0.5) == 0


def test_old_move_set_remains_available(inputs):
    problem, seed, _, _ = inputs
    ctx = Runner(problem, settings={"check_rates": False}).context
    ctx.import_snapshot(seed)
    moves = LayoutMoves(ctx, {**DEFAULTS, "compaction_moves": False})
    assert {op.__name__ for op in moves.operators} == {
        "shift",
        "rotate",
        "swap",
        "cluster",
        "reroute",
    }


def test_benchmark_improvement_records_identical_seeds_and_preserves_outputs(
    inputs, tmp_path
):
    _, seed, planned, netlist = inputs
    source = tmp_path / "source"
    case = source / "small"
    initial = case / "hc/0/first"
    initial.mkdir(parents=True)
    planned.save(case / "plan.json")
    netlist.save(case / "netlist.json")
    (initial / "snapshot.json").write_text(json.dumps(asdict(seed)))
    output = tmp_path / "comparison"
    command = [
        sys.executable,
        str(ROOT / "scripts/dev/benchmark_improvement.py"),
        "--source",
        str(source),
        "--cases",
        "small:0",
        "--output",
        str(output),
        "--seconds",
        "0",
        "--max-actions",
        "1",
        "--backend",
        "python",
    ]
    completed = subprocess.run(
        command, cwd=ROOT, capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0, completed.stderr
    rows = json.loads((output / "summary.json").read_text())
    assert len(rows) == 4
    assert {r["initial_snapshot"] for r in rows} == {seed.id}
    assert all(row["work"]["actions"] == 1 for row in rows)
    assert all(
        row["routed"] and row["assessment"]["rates"] == "not_checked" for row in rows
    )
    before = (output / "summary.json").read_bytes()
    repeated = subprocess.run(
        command, cwd=ROOT, capture_output=True, text=True, check=False
    )
    assert repeated.returncode != 0
    assert (output / "summary.json").read_bytes() == before
