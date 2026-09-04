"""Scenario loading from TOML."""

from fractions import Fraction
from pathlib import Path

from kohakuefda.model.basement import Region
from kohakuefda.model.scenario import PlanMode, Scenario


def test_scenario_from_toml(fixtures_dir: Path) -> None:
    scenario = Scenario.from_toml(fixtures_dir / "scenario_basic.toml")
    assert scenario.supply["item_copper_ore"] == Fraction(120)
    assert scenario.supply["item_liquid_water"] is None
    assert scenario.targets == {"item_copper_enr": Fraction(15)}
    assert scenario.basement.region is Region.WULING
    assert scenario.basement.basement_id == "sky_king_flats"
    assert (scenario.basement.level, scenario.basement.depot_level) == (2, 1)
    assert scenario.mode is PlanMode.AREA
    assert scenario.gas is False and scenario.mixed_lanes is True
    assert scenario.recipe_overrides == {"item_copper_enr": "pool_copper_enr_1"}


def test_scenario_round_trips_through_json(fixtures_dir: Path) -> None:
    scenario = Scenario.from_toml(fixtures_dir / "scenario_basic.toml")
    again = Scenario.model_validate_json(scenario.model_dump_json())
    assert again == scenario
