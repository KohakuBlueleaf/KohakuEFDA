"""Every catalogue solver streams self-contained frames through the real stage, and a cancelled run keeps its last frame."""

import json
from pathlib import Path

import pytest

from kohakuefda.layout.settings import SOLVERS
from kohakuefda.layout.stages import layout_stage, netlist_stage, params_of, plan_stage
from kohakuefda.model.control import CancelledError
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.scenario import Scenario
from kohakuefda.serve.runs import Run, RunManager

ROOT = Path(__file__).resolve().parents[1]
NAMES = [entry["name"] for entry in SOLVERS.describe()]


@pytest.fixture(scope="module")
def dataset():
    return Dataset.load(ROOT / "data/1.5.3@9764758-3/dataset.json")


@pytest.fixture(scope="module")
def scenario():
    return Scenario.from_toml(ROOT / "tests/fixtures/scenario_valley_battery.toml")


@pytest.fixture(scope="module")
def netlist(dataset, scenario):
    return netlist_stage(dataset, scenario, plan_stage(dataset, scenario))


def options(name):
    defaults = SOLVERS.get(name).defaults
    limits = {
        "improvement_steps": 5,
        "construction_steps": 4,
        "until_budget": False,
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
                "seconds": 0,
                "max_actions": 2000,
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
            assert frame["domain"] == "target"
        assert frames[-1]["kind"] == "final" and frames[-1]["outcome"]
        streamed = [e["data"] for e in run.events if e["kind"] == "frame"]
        assert streamed == frames
        restored = Run.read(run.directory)
        assert restored.frames["layout"] == frames
    finally:
        manager.shutdown()


@pytest.mark.parametrize("name", ["hc", "sa", "regional"])
def test_cancellation_preserves_terminal_frame_after_live_observation(
    dataset, netlist, name
):
    flag = [False]
    frames = []

    def observe(frame):
        frames.append(frame)
        if frame.get("placed", 0) > 0 and frame["kind"] != "final":
            flag[0] = True

    with pytest.raises(CancelledError):
        layout_stage(
            dataset,
            netlist,
            params_of(
                "layout",
                {"solver": name, "seconds": 0, "frame_every": 1, "max_actions": 3000},
            ),
            observe,
            lambda: flag[0],
        )
    assert frames[-1]["kind"] == "final"
    assert frames[-1]["outcome"]["status"] == "cancelled"


def test_frame_sampling_does_not_change_the_layout(dataset, netlist):
    layouts = []
    live = {}
    for every in (10, 50):
        frames = []
        _, layout = layout_stage(
            dataset,
            netlist,
            params_of(
                "layout",
                {
                    "solver": "regional",
                    "seconds": 0,
                    "max_actions": 2000,
                    "frame_every": every,
                    "seed": 2,
                },
            ),
            frames.append,
        )
        layouts.append(layout.model_dump())
        assert frames[0]["kind"] == "catalogue" and frames[-1]["kind"] == "final"
        live[every] = sum(f["kind"] in ("build", "improve") for f in frames)
        actions = frames[-1]["outcome"]["work"]["actions"]
        assert live[every] >= actions // every - 2, (every, live[every], actions)
    assert live[10] > live[50]
    assert layouts[0] == layouts[1]
