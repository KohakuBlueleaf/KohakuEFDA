"""Requirements (what the targets need from outside) and outcomes (what leaves the line and
what each could become)."""

from pathlib import Path

import pytest

from kohakuefda.model.dataset import Dataset
from kohakuefda.model.scenario import Scenario
from kohakuefda.plan.outcomes import next_products, outcomes, requirements
from kohakuefda.plan.planner import plan
from kohakuefda.plan.recipes import allowed

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "1.5.3@9764758-3" / "dataset.json"
FIXTURES = ROOT / "tests" / "fixtures"


@pytest.fixture(scope="module")
def dataset() -> Dataset:
    return Dataset.load(DATASET)


def test_requirements_sort_natural_from_gathered(dataset: Dataset) -> None:
    scenario = Scenario.from_toml(FIXTURES / "scenario_valley_battery.toml").model_copy(
        update={
            "basement": Scenario.from_toml(FIXTURES / "scenario_basic.toml").basement
        }
    )
    needs = requirements(dataset, scenario)
    assert {"item_quartz_sand", "item_originium_ore"} <= set(needs.natural)
    assert "item_quartz_glass" in needs.intermediates
    raw = set(needs.natural) | set(needs.gathered)
    assert not raw & set(needs.intermediates)
    assert not set(scenario.targets) & set(needs.intermediates)
    assert all(dataset.is_resource(i) for i in needs.natural)
    assert not any(dataset.is_resource(i) for i in needs.gathered)
    copper = Scenario(targets={"item_copper_cmpt": "min"}, basement=scenario.basement)
    needs = requirements(dataset, copper)
    assert "item_liquid_water" in needs.natural
    assert "item_copper_ore" in needs.natural
    assert "item_liquid_water" not in needs.intermediates


def test_outcomes_cover_every_flow_of_the_plan(dataset: Dataset) -> None:
    scenario = Scenario.from_toml(FIXTURES / "scenario_wuling_hetonite.toml")
    result = plan(dataset, scenario)
    found = outcomes(dataset, scenario, result)
    kinds = {(o.item_id, o.kind) for o in found}
    for item_id, balance in result.items.items():
        if balance.delivered > 0:
            assert (item_id, "delivered") in kinds
        if balance.sunk > 0:
            assert (
                item_id,
                "stored" if balance.sink_kind == "depot" else "dumped",
            ) in kinds
        if balance.supplied > 0:
            assert (item_id, "consumed") in kinds
    dumped = [o for o in found if o.kind == "dumped"]
    assert dumped and all(
        o.sink_machine == dataset.dump_for(o.item_id).machine_id for o in dumped
    )
    order = [o.kind for o in found]
    assert order == sorted(
        order, key=["delivered", "stored", "dumped", "consumed", "missing"].index
    )


def test_next_products_follow_allowed_recipes_and_the_flow(dataset: Dataset) -> None:
    scenario = Scenario.from_toml(FIXTURES / "scenario_valley_battery.toml")
    result = plan(dataset, scenario)
    target = next(
        o for o in outcomes(dataset, scenario, result) if o.kind == "delivered"
    )
    assert target.goal is None
    for option in target.next:
        recipe = dataset.recipes[option.recipe_id]
        assert allowed(dataset, scenario, recipe)
        assert recipe.input_rate(target.item_id) > 0
        assert option.product_id != target.item_id
        assert option.rate == target.rate * option.ratio
        assert target.item_id not in option.inputs
    sand = next_products(dataset, scenario, "item_quartz_sand", target.rate)
    assert any(o.product_id == "item_quartz_glass" for o in sand)
    wuling = Scenario.from_toml(FIXTURES / "scenario_wuling_hetonite.toml")
    assert len(next_products(dataset, wuling, "item_quartz_sand", target.rate)) >= len(
        sand
    )


def test_missing_targets_are_reported(dataset: Dataset) -> None:
    scenario = Scenario.from_toml(FIXTURES / "scenario_valley_battery.toml")
    starved = scenario.model_copy(update={"supply": {}, "natural_default": "none"})
    result = plan(dataset, starved)
    found = outcomes(dataset, starved, result)
    assert [o.kind for o in found if o.item_id == "item_proc_battery_1"] == ["missing"]
