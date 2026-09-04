"""Target intents: a rate, ``min`` (one machine of the maker) and ``max`` (bounded by supply or
by the area budget), and their TOML round trip."""

from fractions import Fraction
from pathlib import Path

import pytest

from kohakuefda.model.basement import Region
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.scenario import BasementRef, PlanMode, Scenario, goal_of
from kohakuefda.plan.lp import AREA_FILL
from kohakuefda.plan.planner import area_budget, plan

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "1.5.3@9764758-3" / "dataset.json"
BATTERY = "item_proc_battery_1"


@pytest.fixture(scope="module")
def dataset() -> Dataset:
    return Dataset.load(DATASET)


def _battery(targets: dict, supply: dict | None = None, **extra) -> Scenario:
    return Scenario(
        supply=supply or {"item_quartz_sand": None, "item_originium_ore": None},
        targets=targets,
        basement=BasementRef(
            region=Region.VALLEY4, basement_id="infra_station", level=2
        ),
        mode=PlanMode.MACHINES,
        gas=False,
        recipe_overrides={"item_quartz_glass": "furnance_quartz_glass_1"},
        **extra,
    )


def _makers(dataset: Dataset, result, item_id: str) -> list:
    return [
        use
        for use in result.recipes
        if use.recipe_id in dataset.recipes
        and dataset.recipes[use.recipe_id].output_rate(item_id) > 0
    ]


def test_min_target_is_one_machine_of_the_maker(dataset: Dataset) -> None:
    result = plan(dataset, _battery({BATTERY: "min"}))
    assert result.status == "ok"
    target = result.targets[0]
    assert target.goal == "min"
    makers = _makers(dataset, result, BATTERY)
    assert len(makers) == 1 and makers[0].machines_exact == 1
    assert target.requested == dataset.recipes[makers[0].recipe_id].output_rate(BATTERY)
    assert target.achieved == target.requested


def test_max_target_is_bounded_by_the_area_budget(dataset: Dataset) -> None:
    scenario = _battery({BATTERY: "max"})
    result = plan(dataset, scenario)
    assert result.status == "ok"
    target = result.targets[0]
    assert target.goal == "max" and target.achieved > 0
    assert target.requested == target.achieved
    budget = area_budget(dataset, scenario)
    square = dataset.basements["infra_station"].square(2)
    assert budget == AREA_FILL * square[0] * square[1]
    covered = sum(
        use.machines_exact
        * dataset.machines[use.machine_id].width
        * dataset.machines[use.machine_id].depth
        for use in result.recipes
    )
    assert float(covered) <= budget + 1e-6
    assert float(covered) > budget * 0.8


def test_max_target_is_bounded_by_the_supply(dataset: Dataset) -> None:
    scenario = _battery(
        {BATTERY: "max"},
        supply={"item_quartz_sand": Fraction(30), "item_originium_ore": None},
    )
    result = plan(dataset, scenario)
    assert result.status == "ok"
    assert result.items["item_quartz_sand"].supplied <= 30
    unlimited = plan(dataset, _battery({BATTERY: "max"}))
    assert result.targets[0].achieved < unlimited.targets[0].achieved


def test_area_fill_scales_the_budget(dataset: Dataset) -> None:
    half = plan(dataset, _battery({BATTERY: "max"}, area_fill=0.25))
    full = plan(dataset, _battery({BATTERY: "max"}, area_fill=0.5))
    assert half.targets[0].achieved < full.targets[0].achieved


def test_rated_and_open_targets_mix(dataset: Dataset) -> None:
    result = plan(dataset, _battery({BATTERY: Fraction(3), "item_quartz_glass": "max"}))
    assert result.status == "ok"
    by_item = {t.item_id: t for t in result.targets}
    assert by_item[BATTERY].achieved == 3 and by_item[BATTERY].goal is None
    assert by_item["item_quartz_glass"].goal == "max"
    assert by_item["item_quartz_glass"].achieved > 0


def test_goal_targets_round_trip_toml(dataset: Dataset) -> None:
    scenario = _battery({BATTERY: "min", "item_quartz_glass": "max"}, area_fill=0.4)
    text = scenario.to_toml()
    assert 'item_proc_battery_1 = "min"' in text
    assert "area_fill = 0.4" in text
    back = Scenario.from_toml_text(text)
    assert back == scenario
    assert goal_of(back.targets[BATTERY]) == "min"
    assert goal_of(Fraction(3)) is None
    dumped = scenario.model_dump(mode="json")
    assert dumped["targets"] == {BATTERY: "min", "item_quartz_glass": "max"}
    assert Scenario.model_validate(dumped) == scenario
