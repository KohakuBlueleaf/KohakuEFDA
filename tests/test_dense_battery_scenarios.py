"""Dense battery inputs and sustainable material plans; REG-04, PLT-01, RES-02."""

from fractions import Fraction
from pathlib import Path

import pytest

from kohakuefda.layout.board import board_of
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.scenario import Scenario
from kohakuefda.plan.netlist import build_netlist
from kohakuefda.plan.planner import plan

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "1.5.3@9764758-3" / "dataset.json"
CASES = (
    ("valley6", "item_proc_battery_3", 6, 70),
    ("valley12", "item_proc_battery_3", 12, 70),
    ("valley18", "item_proc_battery_3", 18, 70),
    ("wuling6", "item_proc_battery_5", 6, 80),
    ("wuling12", "item_proc_battery_5", 12, 80),
)
WOOD = "item_plant_tundra_wood"


@pytest.fixture(scope="module")
def dataset() -> Dataset:
    return Dataset.load(DATASET)


@pytest.mark.parametrize("name,item,rate,side", CASES)
def test_dense_battery_inputs(dataset, fixtures_dir, name, item, rate, side):
    scenario = Scenario.from_toml(fixtures_dir / f"scenario_dense_{name}.toml")
    assert scenario.targets == {item: Fraction(rate)}
    assert scenario.supply[WOOD] == 0
    assert not scenario.gas
    assert scenario.gas_default == "none"
    assert scenario.natural_default == "none"
    assert not scenario.core
    assert scenario.depot == "bus"
    x0, y0, x1, y1 = board_of(dataset, scenario).area
    assert (x1 - x0, y1 - y0) == (side, side)
    assert Scenario.from_toml_text(scenario.to_toml()) == scenario


@pytest.mark.parametrize("name,item,rate,side", CASES)
def test_dense_battery_plan_uses_only_declared_supply(
    dataset, fixtures_dir, name, item, rate, side
):
    scenario = Scenario.from_toml(fixtures_dir / f"scenario_dense_{name}.toml")
    result = plan(dataset, scenario)
    assert result.status == "ok", result.findings
    assert len(result.targets) == 1
    assert result.targets[0].requested == result.targets[0].achieved == rate
    assert result.zones == {}
    supplied = {i for i, balance in result.items.items() if balance.supplied}
    assert supplied <= {i for i, supply in scenario.supply.items() if supply is None}
    assert WOOD not in supplied
    machines = {use.machine_id for use in result.recipes}
    assert {"planter_1", "seedcollector_1"} <= machines
    netlist = build_netlist(dataset, scenario, result)
    assert netlist.scenario == scenario
    assert all(len(cell.machines) <= 1 for cell in netlist.cells)
