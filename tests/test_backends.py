"""The layout stage answers the same on the Python kernel and on the native twin."""

from pathlib import Path

import pytest

from kohakuefda.layout.stages import layout_stage, netlist_stage, plan_stage
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.scenario import Scenario

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def dataset() -> Dataset:
    return Dataset.load(ROOT / "data" / "1.5.3@9764758-3" / "dataset.json")


def test_a_layout_run_routes_the_same_on_either_kernel(dataset: Dataset) -> None:
    pytest.importorskip("kohakulayout_rs")
    scenario = Scenario.from_toml(
        ROOT / "tests" / "fixtures" / "scenario_gas_xiranite.toml"
    )
    netlist = netlist_stage(dataset, scenario, plan_stage(dataset, scenario))
    layouts = []
    for backend in ("python", "native"):
        _, layout = layout_stage(
            dataset,
            netlist,
            {
                "solver": "regional",
                "seconds": 0,
                "max_actions": 4000,
                "backend": backend,
                "seed": 1,
            },
        )
        layouts.append(layout.model_dump())
    assert layouts[0] == layouts[1]
