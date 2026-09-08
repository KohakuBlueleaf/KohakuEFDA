"""Studio submits typed solver controls and distinguishes incomplete searches from errors."""

import json
from pathlib import Path

import pytest

from kohakuefda.layout.engine import LAYOUT_DEFAULTS, SOLVERS, solver_of
from kohakuefda.layout.stages import StageError, params_of
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.scenario import Scenario
from kohakuefda.serve.runs import Run, RunError, RunManager

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def dataset():
    return Dataset.load(ROOT / "data/1.5.3@9764758-3/dataset.json")


@pytest.fixture(scope="module")
def scenario():
    return Scenario.from_toml(ROOT / "tests/fixtures/scenario_valley_battery.toml")


def prepared(dataset, scenario, tmp_path):
    manager = RunManager(dataset, tmp_path)
    run = manager.create(scenario)
    manager._execute(run, ["plan", "netlist"])
    assert run.stages["netlist"].status == "done"
    return manager, run


def test_default_layout_is_hill_climbing_on_a_time_budget():
    params = params_of("layout")
    assert params["solver"] == "hc"
    assert params["seconds"] == 600
    assert params["backend"] == "auto" and params["seed"] == 0
    assert params["max_actions"] == 0
    solver_id, options = solver_of(params)
    assert solver_id == "climb" and options == {}
    assert SOLVERS.get("hc").defaults["until_budget"] is True
    assert params["solver_options"] == LAYOUT_DEFAULTS["solver_options"] == "{}"


def test_ui_payload_keeps_booleans_and_explicit_solver_overrides():
    params = params_of(
        "layout",
        {
            "solver": "sa",
            "seconds": 300,
            "max_actions": 0,
            "workers": 1,
            "solver_options": json.dumps(
                {
                    "until_budget": False,
                    "construction_temperature": 2.5,
                    "repack_every": 32,
                    "improvement_steps": 0,
                }
            ),
        },
    )
    solver_id, options = solver_of(params)
    assert solver_id == "anneal"
    assert options["until_budget"] is False
    assert options["construction_temperature"] == 2.5
    assert options["repack_every"] == 32
    assert options["improvement_steps"] == 0
    _, baseline = solver_of(
        params_of(
            "layout",
            {
                "solver": "baseline",
                "spread_attempts": 2,
                "solver_options": '{"spread_attempts": 17}',
            },
        )
    )
    assert baseline["spread_attempts"] == 17
    _, regional = solver_of(
        params_of("layout", {"solver": "regional", "spread_attempts": 9})
    )
    assert regional["attempts"] == 9


@pytest.mark.parametrize(
    "values",
    [
        {"seconds": -1},
        {"seconds": float("nan")},
        {"max_actions": 1.5},
        {"solver": "hc", "solver_options": "null"},
        {"solver": "hc", "solver_options": "[]"},
        {"solver": "hc", "solver_options": "{"},
        {"solver": "hc", "solver_options": '{"until_budget":"false"}'},
        {"solver": "hc", "solver_options": '{"repack_size":1}'},
        {"solver": "hc", "solver_options": '{"no_such_option":1}'},
        {"solver": "baseline", "solver_options": '{"spread_attempts":65536}'},
        {"solver": "no-such-solver"},
    ],
)
def test_invalid_controls_are_rejected_before_queueing(values):
    with pytest.raises(StageError):
        params_of("layout", values)


def test_incomplete_outcome_and_settings_survive_reload_and_block_verify(
    dataset, scenario, tmp_path
):
    manager, run = prepared(dataset, scenario, tmp_path)
    run.stages["layout"].params = params_of(
        "layout", {"solver": "hc", "max_actions": 1}
    )
    manager._execute(run, ["layout", "verify"])
    state = run.stages["layout"]
    assert state.status == "incomplete"
    assert state.error == ""
    assert state.outcome["status"] == "budget_exhausted"
    assert not state.outcome["routed"]
    assert state.outcome["work"]["actions"] >= 1
    assert state.outcome["settings"]["runtime"]["max_actions"] == 1
    assert state.outcome["settings"]["solver_settings"] == {}
    assert run.frames["layout"][-1]["outcome"] == state.outcome
    assert run.stages["verify"].status == "idle"
    restored = Run.read(run.directory)
    assert restored.stages["layout"].to_dict() == state.to_dict()
    assert restored.stages["verify"].status == "idle"
    with pytest.raises(RunError, match="layout"):
        manager.start(run.id, "verify")


def test_a_routed_layout_is_done_whatever_ended_the_search(dataset, scenario, tmp_path):
    manager, run = prepared(dataset, scenario, tmp_path)
    run.stages["layout"].params = params_of(
        "layout", {"solver": "regional", "max_actions": 3000}
    )
    manager._execute(run, ["layout"])
    state = run.stages["layout"]
    assert state.status == "done", state.to_dict()
    assert state.outcome["routed"]
    assert state.outcome["placed"] == state.outcome["total"]
    assert state.outcome["work"]["actions"] <= 3000
    assert "layout" in run.artifacts
    assert run.frames["layout"][-1]["clean"]


def test_real_execution_fault_is_still_failed(dataset, scenario, tmp_path):
    manager, run = prepared(dataset, scenario, tmp_path)
    run.stages["layout"].params = params_of(
        "layout", {"solver": "hc", "backend": "no-such-kernel"}
    )
    manager._execute(run, ["layout", "verify"])
    assert run.stages["layout"].status == "failed"
    assert run.stages["layout"].error
    assert run.stages["layout"].outcome is None
    assert run.stages["verify"].status == "idle"


def test_legacy_partial_done_frames_are_reclassified_without_rewriting_files(
    scenario, tmp_path
):
    directory = tmp_path / "legacy"
    run = Run("legacy", scenario, directory)
    run.stages["layout"].status = "done"
    run.frames["layout"] = [
        {
            "kind": "final",
            "status": "no_solution_found",
            "evidence": {"routed": False},
            "placed": 121,
            "total": 123,
            "elapsed": 5,
        }
    ]
    run.write_stage("layout")
    before = (directory / "run.json").read_bytes()
    restored = Run.read(directory)
    assert restored.stages["layout"].status == "incomplete"
    assert restored.stages["layout"].outcome["placed"] == 121
    assert (directory / "run.json").read_bytes() == before
