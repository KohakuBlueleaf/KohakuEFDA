"""Logical planner: machine counts, balances, sinks, degrade and filters."""

from fractions import Fraction
from pathlib import Path

import pytest

from kohakuefda.flow.lanes import machines_per_lane
from kohakuefda.model.basement import Region
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.scenario import BasementRef, PlanMode, Scenario
from kohakuefda.plan.planner import plan
from kohakuefda.plan.recipes import allowed, expand

DATASET = (
    Path(__file__).resolve().parents[1] / "data" / "1.5.3@9764758-3" / "dataset.json"
)
WULING = BasementRef(
    region=Region.WULING, basement_id="sky_king_flats", level=2, depot_level=1
)
VALLEY = BasementRef(
    region=Region.VALLEY4, basement_id="infra_station", level=1, depot_level=1
)


@pytest.fixture(scope="module")
def dataset() -> Dataset:
    return Dataset.load(DATASET)


def item_by_name(dataset: Dataset, name: str) -> str:
    return next(i.id for i in dataset.items.values() if i.names.en == name)


def test_fixture_scenario_plans_hetonite(dataset: Dataset, fixtures_dir: Path) -> None:
    scenario = Scenario.from_toml(fixtures_dir / "scenario_basic.toml")
    result = plan(dataset, scenario)
    assert result.status == "ok" and result.scale == 1
    assert result.targets[0].achieved == Fraction(15)
    sewage = result.items["item_liquid_sewage"]
    assert (sewage.sunk, sewage.sink_kind) == (Fraction(135), "dump")
    dump = next(u for u in result.recipes if u.machine_id == "liquid_cleaner_1")
    assert (dump.machines_exact, dump.machines) == (Fraction(9, 2), 5)
    assert all(b.net == 0 for b in result.items.values())
    ore_net = next(n for n in result.nets if n.item_id == "item_copper_ore")
    assert (ore_net.source, ore_net.rate, ore_net.lanes) == ("supply", Fraction(120), 4)
    water_net = next(n for n in result.nets if n.item_id == "item_liquid_water")
    assert water_net.fluid and water_net.lanes == 1
    assert result.machine_count == sum(u.machines for u in result.recipes)
    assert any(f.rule == "plan.power" for f in result.findings)
    assert result.power > 200


def test_single_recipe_line_rounds_machines_up(dataset: Dataset) -> None:
    origocrust = item_by_name(dataset, "Origocrust")
    scenario = Scenario(
        supply={"item_originium_ore": None},
        targets={origocrust: Fraction(45)},
        basement=WULING,
        mode=PlanMode.MACHINES,
        gas=False,
    )
    result = plan(dataset, scenario)
    assert result.status == "ok"
    (use,) = [u for u in result.recipes if u.machine_id == "furnance_1"]
    assert (use.machines_exact, use.machines) == (Fraction(3, 2), 2)
    assert result.items["item_originium_ore"].supplied == Fraction(45)
    assert result.items[origocrust].delivered == Fraction(45)
    recipe = dataset.recipes[use.recipe_id]
    assert machines_per_lane(dataset, recipe, "item_originium_ore") == 1


def test_short_supply_degrades_targets(dataset: Dataset) -> None:
    origocrust = item_by_name(dataset, "Origocrust")
    scenario = Scenario(
        supply={"item_originium_ore": Fraction(20)},
        targets={origocrust: Fraction(45)},
        basement=WULING,
        gas=False,
    )
    result = plan(dataset, scenario)
    assert result.status == "degraded"
    assert result.targets[0].achieved == Fraction(20)
    assert result.scale == Fraction(4, 9)
    assert any(f.rule == "plan.degraded" for f in result.findings)


def test_fluid_byproduct_without_sink_blocks_production(dataset: Dataset) -> None:
    scenario = Scenario(
        supply={"item_liquid_copper": None},
        targets={"item_liquid_copper_enr": Fraction(30)},
        basement=WULING,
        gas=False,
        natural_default="none",
    )
    result = plan(dataset, scenario)
    assert result.status == "infeasible"
    assert result.targets[0].achieved == 0
    recycled = plan(dataset, scenario.model_copy(update={"natural_default": "plenty"}))
    assert recycled.status == "ok"
    assert recycled.items["item_liquid_acid"].sunk == 0


def test_fluid_target_is_flagged(dataset: Dataset) -> None:
    scenario = Scenario(
        supply={"item_copper_ore": None, "item_liquid_water": None},
        targets={"item_liquid_copper": Fraction(30)},
        basement=WULING,
        gas=False,
        recipe_overrides={"item_liquid_copper": "pool_liquid_copper_1"},
    )
    result = plan(dataset, scenario)
    assert result.status in ("ok", "degraded", "infeasible")
    if (
        result.items.get("item_liquid_copper")
        and result.items["item_liquid_copper"].delivered
    ):
        assert any(f.rule == "flow.fluid_target" for f in result.findings)


def test_region_and_gas_filters(dataset: Dataset) -> None:
    wuling = Scenario(targets={}, basement=WULING)
    valley = Scenario(targets={}, basement=VALLEY)
    no_gas = Scenario(targets={}, basement=WULING, gas=False)
    crucible = dataset.recipes["pool_copper_enr_1"]
    assert allowed(dataset, wuling, crucible)
    assert not allowed(dataset, valley, crucible)
    env_recipe = next(r for r in dataset.recipes.values() if r.env and not r.event)
    assert allowed(dataset, wuling, env_recipe)
    assert not allowed(dataset, no_gas, env_recipe)
    event_recipe = next(r for r in dataset.recipes.values() if r.event)
    assert not allowed(dataset, wuling, event_recipe)
    assert allowed(dataset, wuling.model_copy(update={"events": True}), event_recipe)
    solid = next(
        r
        for r in dataset.recipes.values()
        if r.machine_id == "grinder_1" and r.mode == "normal"
    )
    assert allowed(dataset, valley, solid)


def test_expand_reaches_raw_items(dataset: Dataset, fixtures_dir: Path) -> None:
    scenario = Scenario.from_toml(fixtures_dir / "scenario_basic.toml")
    graph = expand(dataset, scenario)
    assert "pool_copper_enr_1" in graph.recipe_ids
    assert set(graph.raw_items) >= {
        "item_copper_ore",
        "item_iron_ore",
        "item_liquid_water",
    }
