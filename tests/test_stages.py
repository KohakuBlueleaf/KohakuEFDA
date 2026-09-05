"""The staged pipeline: checkpoints between stages, frames, parameters, reruns, cancellation."""

from pathlib import Path

import pytest

from kohakuefda.layout.stages import (
    STAGES,
    StageError,
    layout_stage,
    netlist_stage,
    params_of,
    plan_stage,
    verify_stage,
)
from kohakuefda.model.control import CancelledError
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.placement import Placement
from kohakuefda.model.scenario import Scenario

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "1.5.3@9764758-3" / "dataset.json"


@pytest.fixture(scope="module")
def dataset() -> Dataset:
    return Dataset.load(DATASET)


@pytest.fixture(scope="module")
def netlist(dataset: Dataset):
    scenario = Scenario.from_toml(
        ROOT / "tests" / "fixtures" / "scenario_valley_battery.toml"
    )
    plan = plan_stage(dataset, scenario)
    return plan, netlist_stage(dataset, scenario, plan)


def test_stage_order_and_parameter_defaults() -> None:
    assert STAGES == ("plan", "netlist", "layout", "verify")
    params = params_of("layout", {"restarts": "2", "seed": 3})
    assert params["restarts"] == 2 and params["seed"] == 3
    assert params["spread_gap"] == 0 and params["w_wire"] == 1.0
    assert params["pylon"] == "power_diffuser_1" and params["entry_sides"] == "NW"
    with pytest.raises(StageError):
        params_of("layout", {"bogus": 1})
    with pytest.raises(StageError):
        params_of("place")


def test_layout_stage_records_frames_and_a_checkpoint(
    dataset: Dataset, netlist, tmp_path: Path
) -> None:
    plan, built = netlist
    frames: list[dict] = []
    placement, layout = layout_stage(
        dataset,
        built,
        {"restarts": 1, "frame_every": 10},
        frames.append,
    )
    catalogue = frames[0]
    assert catalogue["kind"] == "catalogue"
    assert {b["id"] for b in catalogue["blocks"]} == {b.id for b in placement.blocks}
    assert catalogue["area"] == list(placement.area)
    assert catalogue["grid"] == list(placement.grid)
    assert catalogue["slots"]
    building = [f for f in frames if f["kind"] == "build"]
    assert building and all("blocks" in f and "cost" in f for f in building)
    assert any(f["clean"] for f in building)
    assert frames[-1]["kind"] == "final" and frames[-1]["fits"]
    assert set(placement.terms) >= {"area", "waste", "length", "pylons", "junctions"}
    last = {b[0]: b[1:] for b in frames[-1]["blocks"]}
    for block in placement.blocks:
        assert last[block.id] == [block.x, block.y, block.rotation]
    assert layout.width == placement.grid[0]
    assert layout.area == placement.area
    assert placement.pylons
    assert any(m.machine_id == "power_diffuser_1" for m in layout.machines)
    assert placement.cost > 0
    placement.save(tmp_path / "placement.json")
    restored = Placement.load(tmp_path / "placement.json")
    assert restored.blocks == placement.blocks and restored.entries == placement.entries
    report, evaluation = verify_stage(dataset, plan, built, placement, layout)
    assert report.ok, [f for f in report.findings if f.severity == "error"]
    assert evaluation is not None and evaluation.converged


def test_layout_is_reproducible_for_a_seed(dataset: Dataset, netlist) -> None:
    _, built = netlist
    settings = {"restarts": 1, "seed": 5}
    first = layout_stage(dataset, built, settings)[1]
    again = layout_stage(dataset, built, settings)[1]
    assert first.model_dump() == again.model_dump()


def test_cancellation_stops_the_layout(dataset: Dataset, netlist) -> None:
    _, built = netlist
    with pytest.raises(CancelledError):
        layout_stage(dataset, built, {"restarts": 1}, None, lambda: True)
