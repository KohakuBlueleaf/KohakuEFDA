"""Plans a player would build: whole machines, conserved items, the direct recipe over a chain
of converters, activation per built machine, no hand-gathered wood, power as a total only,
banned phases and machines."""

from fractions import Fraction
from pathlib import Path

import pytest

from kohakuefda.model.basement import Region
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.plan import Plan
from kohakuefda.model.scenario import BasementRef, PlanMode, Scenario
from kohakuefda.plan.outcomes import requirements
from kohakuefda.plan.planner import plan
from kohakuefda.plan.recipes import allowed

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "1.5.3@9764758-3" / "dataset.json"
FIXTURES = ROOT / "tests" / "fixtures"
WULING = BasementRef(
    region=Region.WULING, basement_id="cardiac_remediation_station", level=3
)
NATURAL = {
    "item_originium_ore": None,
    "item_iron_ore": None,
    "item_quartz_sand": None,
    "item_copper_ore": None,
    "item_liquid_water": None,
    "item_liquid_acid": None,
}


@pytest.fixture(scope="module")
def dataset() -> Dataset:
    return Dataset.load(DATASET)


def _conserved(result: Plan) -> None:
    for balance in result.items.values():
        assert balance.net == 0, balance
        assert balance.produced + balance.supplied == (
            balance.consumed + balance.delivered + balance.sunk
        ), balance


def _whole(dataset: Dataset, result: Plan) -> None:
    for use in result.recipes:
        assert use.machines == int(use.machines) and use.machines >= 1
        if use.recipe_id in dataset.recipes:
            capacity = dataset.recipes[use.recipe_id].crafts_per_minute * use.machines
            assert use.crafts_per_min <= capacity
            assert use.machines_exact <= use.machines


def _machines_of(result: Plan, machine_id: str) -> int:
    return sum(u.machines for u in result.recipes if u.machine_id == machine_id)


def test_battery_line_is_whole_and_conserved(dataset: Dataset) -> None:
    scenario = Scenario.from_toml(FIXTURES / "scenario_wuling_battery4.toml")
    result = plan(dataset, scenario)
    assert result.status == "ok", result.findings
    _conserved(result)
    _whole(dataset, result)
    assert _machines_of(result, "tools_assebling_mc_1") == 1
    assert _machines_of(result, "planter_1") >= 1
    assert _machines_of(result, "seedcollector_1") >= 1
    assert "item_plant_tundra_wood" not in result.items
    assert result.power == sum(
        u.machines * dataset.machines[u.machine_id].power
        for u in result.recipes
        if not u.recipe_id.startswith("dump:")
    )


def test_script_line_uses_the_crucible_not_a_transmuter_chain(dataset: Dataset) -> None:
    scenario = Scenario.from_toml(FIXTURES / "scenario_wuling_script.toml")
    result = plan(dataset, scenario)
    assert result.status in ("ok", "degraded"), result.findings
    _conserved(result)
    _whole(dataset, result)
    recipes = {u.recipe_id for u in result.recipes}
    assert "liquid_transmuter_1_liquid_liquid_xiranite_1" not in recipes
    assert "liquid_transmuter_2_gas_gas_xiranite_1" not in recipes
    if "item_liquid_xiranite" in result.items:
        assert "pool_liquid_liquid_xiranite_1" in recipes
    assert _machines_of(result, "winder_1") == 1


def test_activation_is_charged_per_built_machine(dataset: Dataset) -> None:
    scenario = Scenario(
        supply={**NATURAL, "item_xiranite_powder": None},
        targets={"item_gas_xiranite": Fraction(20)},
        basement=WULING,
        mode=PlanMode.MACHINES,
        recipe_overrides={
            "item_gas_xiranite": "liquid_transmuter_2_gas_gas_xiranite_1"
        },
    )
    result = plan(dataset, scenario)
    assert result.status == "ok", result.findings
    _conserved(result)
    use = next(u for u in result.recipes if u.machine_id == "transmuter_2")
    activation = dataset.activations["transmuter_2"]
    gas = result.items["item_gas_xiranite"]
    assert gas.consumed == activation.min_rate * use.machines
    assert gas.delivered == 20


def test_carbon_comes_from_the_plant_loop_not_wood(dataset: Dataset) -> None:
    scenario = Scenario(
        supply=dict(NATURAL),
        targets={"item_carbon_mtl": Fraction(30)},
        basement=WULING,
        mode=PlanMode.MACHINES,
    )
    needs = requirements(dataset, scenario)
    assert "item_plant_tundra_wood" in needs.gathered
    assert "item_originium_ore" not in needs.gathered
    result = plan(dataset, scenario)
    assert result.status == "ok", result.findings
    _conserved(result)
    _whole(dataset, result)
    assert "item_plant_tundra_wood" not in result.items
    assert _machines_of(result, "planter_1") >= 1
    assert _machines_of(result, "seedcollector_1") >= 1


def test_sewage_is_treated_not_bottled_into_the_depot(dataset: Dataset) -> None:
    scenario = Scenario.from_toml(FIXTURES / "scenario_basic.toml")
    result = plan(dataset, scenario)
    assert result.status == "ok", result.findings
    _conserved(result)
    stored = [b for b in result.items.values() if b.sink_kind == "depot"]
    assert stored == [], [b.item_id for b in stored]
    sewage = result.items["item_liquid_sewage"]
    assert sewage.sink_kind == "dump" and sewage.sunk == 135
    assert "filling_bottled_iron_sewage" not in {u.recipe_id for u in result.recipes}


def test_liquids_and_machine_bans_filter_recipes(dataset: Dataset) -> None:
    base = Scenario(targets={}, basement=WULING)
    crucible = dataset.recipes["pool_liquid_liquid_xiranite_1"]
    furnace = dataset.recipes["furnance_iron_nugget_1"]
    assert allowed(dataset, base, crucible)
    no_liquids = base.model_copy(update={"liquids": False})
    assert not allowed(dataset, no_liquids, crucible)
    assert allowed(dataset, no_liquids, furnace)
    banned = base.model_copy(update={"banned_machines": ["mix_pool_1"]})
    assert not allowed(dataset, banned, crucible)
    assert allowed(dataset, banned, dataset.recipes["pool_liquid_liquid_xiranite_2"])
    text = banned.to_toml()
    assert 'banned_machines = ["mix_pool_1"]' in text and "liquids = true" in text
    assert Scenario.from_toml_text(text) == banned


def test_no_generation_is_planned_only_the_total_requirement(dataset: Dataset) -> None:
    scenario = Scenario(
        supply=dict(NATURAL),
        targets={"item_originium_enr_powder": Fraction(180)},
        basement=WULING,
        mode=PlanMode.MACHINES,
    )
    result = plan(dataset, scenario)
    assert result.status == "ok", result.findings
    _conserved(result)
    assert result.power > 200
    assert all(u.machine_id != "power_station_1" for u in result.recipes)
    assert not any(n.target == "power" for n in result.nets)
    ore = result.items["item_originium_ore"]
    assert ore.consumed == sum(
        dataset.recipes[u.recipe_id].input_rate("item_originium_ore")
        * u.crafts_per_min
        / dataset.recipes[u.recipe_id].crafts_per_minute
        for u in result.recipes
        if u.recipe_id in dataset.recipes
    )
