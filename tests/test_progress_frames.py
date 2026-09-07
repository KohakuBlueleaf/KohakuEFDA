"""Every catalog solver supplies truthful self-contained streamed and replayable frames."""

import json
from pathlib import Path

import pytest

from kohakuefda.framework import problem_of
from kohakuefda.framework.runtime import Runner
from kohakuefda.framework.workspace import Workspace
from kohakuefda.layout.board import board_of
from kohakuefda.layout.engine import Engine
from kohakuefda.layout.stages import params_of
from kohakuefda.model.control import CancelledError
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.scenario import Scenario
from kohakuefda.plan.netlist import build_netlist
from kohakuefda.plan.planner import plan
from kohakuefda.serve.runs import Run, RunManager
from kohakuefda.solvers import SOLVERS

ROOT = Path(__file__).resolve().parents[1]
NAMES = [entry["name"] for entry in SOLVERS.describe()]


@pytest.fixture(scope="module")
def dataset():
    return Dataset.load(ROOT / "data/1.5.3@9764758-3/dataset.json")


@pytest.fixture(scope="module")
def scenario():
    return Scenario.from_toml(ROOT / "tests/fixtures/scenario_valley_battery.toml")


def prepared(dataset, scenario):
    planned = plan(dataset, scenario)
    return build_netlist(dataset, scenario, planned)


def options(name):
    defaults = SOLVERS.get(name).defaults
    limits = {
        "improvement_steps": 5,
        "construction_steps": 4,
        "attempts": 4,
        "shrink_rounds": 3,
        "spread_attempts": 4,
        "spread_slice": 2,
    }
    return {key: value for key, value in limits.items() if key in defaults}


@pytest.mark.parametrize("name", NAMES)
def test_every_solver_streams_checked_frames_through_real_stage(
    dataset, scenario, tmp_path, name
):
    manager = RunManager(dataset, tmp_path)
    run = manager.create(scenario)
    try:
        manager._execute(run, ["plan", "netlist"])
        run.stages["layout"].params = params_of(
            "layout",
            {
                "solver": name,
                "frame_every": 1,
                "solver_options": json.dumps(options(name)),
                "workers": 1,
            },
        )
        manager._execute(run, ["layout"])
        frames = run.frames["layout"]
        assert run.stages["layout"].status in ("done", "incomplete"), run.stages[
            "layout"
        ].error
        assert frames[0]["kind"] == "catalogue"
        live = [f for f in frames if f["kind"] in ("build", "improve")]
        assert len(live) > 1
        for frame in live:
            assert frame["frame_schema"] == 1
            assert frame["grid"] == [
                frame["layout"]["width"],
                frame["layout"]["height"],
            ]
            assert frame["area"] == list(frame["layout"]["area"])
            assert "target_area" in frame and "fixed" in frame and "slots" in frame
            assert frame["placed"] == len(frame["blocks"])
            assert "work" in frame and "elapsed" in frame and "phase" in frame
            if frame["domain"] == "workspace":
                assert not frame["clean"] and not frame["evidence"]["routed"]
            if frame.get("best"):
                assert frame["best"]["state_id"]
        if name.endswith("outline"):
            assert any(f["phase"] == "expansion" for f in live)
        assert frames[-1]["kind"] == "final" and frames[-1]["outcome"]
        streamed = [e["data"] for e in run.events if e["kind"] == "frame"]
        assert streamed == frames
        restored = Run.read(run.directory)
        assert restored.frames["layout"] == frames
    finally:
        manager.shutdown()


def test_parallel_baseline_forwards_live_worker_geometry(dataset, scenario):
    netlist = prepared(dataset, scenario)
    frames = []
    engine = Engine(
        dataset,
        netlist,
        board_of(dataset, scenario),
        params_of(
            "layout",
            {
                "workers": 2,
                "frame_every": 1,
                "solver_options": json.dumps(options("baseline")),
            },
        ),
    )
    engine.run(frames.append)
    workers = [f for f in frames if f.get("display") == "worker"]
    assert workers and any(f["placed"] for f in workers)
    assert all(
        f["phase"] == "parallel" and "worker" in f and "worker_work" in f
        for f in workers
    )
    assert any(f.get("milestone") == "worker_selected" for f in frames)
    assert frames[-1]["outcome"]["routed"]


def test_workspace_resize_frames_keep_original_target_and_realized_routes(
    dataset, scenario
):
    netlist = prepared(dataset, scenario)
    events = []
    parent = Runner(
        problem_of(dataset, netlist),
        settings={"check_rates": False},
        observe=events.append,
    ).context
    first = Workspace(parent, 10)
    block_id = next(
        i for i, b in parent.blocks.items() if b.constraint == "free" and not b.group
    )
    x0, y0, _, _ = first.context.area
    assert (
        first.context.builder().place(block_id, (x0 + 4, y0 + 4, 0)).status == "placed"
    )
    snapshot = first.context.builder().diagnostic()
    larger = Workspace(parent, 20)
    larger.transfer(snapshot)
    larger.context.frame("improve", snapshot=larger.context.diagnostic, force=True)
    frames = [json.loads(e.payload_json) for e in events if e.kind == "frame"]
    assert len({tuple(f["grid"]) for f in frames}) == 2
    assert all(tuple(f["target_area"]) == parent.area for f in frames)
    assert frames[-1]["phase"] == "compaction" and frames[-1]["placed"] == 1
    assert not frames[-1]["clean"]


@pytest.mark.parametrize(
    "name", ["hc", "sa", "hc-tree", "sa-tree", "hc-outline", "sa-outline"]
)
def test_cancellation_preserves_terminal_frame_after_live_observation(
    dataset, scenario, name
):
    netlist = prepared(dataset, scenario)
    flag = [False]
    frames = []

    def observe(frame):
        frames.append(frame)
        if frame.get("placed", 0) > 0 and frame["kind"] != "final":
            flag[0] = True

    engine = Engine(
        dataset,
        netlist,
        board_of(dataset, scenario),
        params_of(
            "layout",
            {
                "solver": name,
                "frame_every": 1,
                "max_actions": 3000,
            },
        ),
    )
    with pytest.raises(CancelledError):
        engine.run(observe, lambda: flag[0])
    assert frames[-1]["kind"] == "final"
    assert frames[-1]["outcome"]["status"] == "cancelled"


def test_frame_sampling_does_not_change_action_limited_solver_results(
    dataset, scenario
):
    problem = problem_of(dataset, prepared(dataset, scenario))
    results = []
    counts = []
    for every in (0, 1, 20):
        events = []
        runner = Runner(
            problem,
            settings={"max_actions": 300, "check_rates": False},
            world={"frame_every": every},
            observe=events.append,
        )
        results.append(runner.run(SOLVERS.get("sa").build()))
        counts.append(sum(e.kind in ("build", "improve") for e in events))
    assert counts[0] < counts[1]
    anchors = [json.loads(r.current.payload)["anchors"] for r in results]
    assert anchors[0] == anchors[1] == anchors[2]
    assert results[0].work == results[1].work == results[2].work
