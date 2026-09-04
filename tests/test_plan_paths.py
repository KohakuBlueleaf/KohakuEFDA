"""The planner picks the least-machine path under the scenario's constraints: a crucible over a
transmuter chain, gas off never blocks a liquid line nor marks its products as hand-gathered,
ores feed their own refiners, allowing gas never costs more, natural resources are offered by
default, power is a total requirement only, event recipes stay out."""

from fractions import Fraction
from pathlib import Path

import pytest

from kohakuefda.model.basement import Region
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.plan import Plan
from kohakuefda.model.scenario import BasementRef, PlanMode, Scenario
from kohakuefda.plan.outcomes import requirements
from kohakuefda.plan.planner import plan

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "1.5.3@9764758-3" / "dataset.json"
WULING = BasementRef(region=Region.WULING, basement_id="sky_king_flats", level=3)
NATURAL: dict[str, Fraction | None] = {
    "item_originium_ore": None,
    "item_iron_ore": None,
    "item_quartz_sand": None,
    "item_copper_ore": None,
    "item_liquid_water": None,
    "item_liquid_acid": None,
    "item_gas_inert": None,
    "item_gas_xiranite": None,
}
GAS_MACHINES = {"transmuter_1", "transmuter_2", "gas_reactor_1", "vaporizer_1"}


@pytest.fixture(scope="module")
def dataset() -> Dataset:
    return Dataset.load(DATASET)


def _machines(result: Plan) -> set[str]:
    return {u.machine_id for u in result.recipes}


def _recipes(result: Plan) -> set[str]:
    return {u.recipe_id for u in result.recipes}


def _conserved(result: Plan) -> None:
    for balance in result.items.values():
        assert balance.net == 0, balance


@pytest.mark.parametrize("gas", [True, False])
@pytest.mark.parametrize("mode", list(PlanMode))
def test_liquid_xiranite_is_one_crucible(
    dataset: Dataset, gas: bool, mode: PlanMode
) -> None:
    scenario = Scenario(
        supply={"item_xiranite_powder": None, "item_liquid_water": None},
        targets={"item_liquid_xiranite": Fraction(30)},
        basement=WULING,
        mode=mode,
        gas=gas,
    )
    result = plan(dataset, scenario)
    assert result.status == "ok", result.findings
    _conserved(result)
    assert _machines(result) == {"mix_pool_1"}
    assert result.machine_count == 1
    assert result.items["item_liquid_xiranite"].delivered == 30


@pytest.mark.parametrize("mode", list(PlanMode))
def test_hetonite_without_gas_comes_from_hetonite_solution(
    dataset: Dataset, mode: PlanMode
) -> None:
    scenario = Scenario(
        supply=dict(NATURAL),
        targets={"item_copper_enr": Fraction(6)},
        basement=WULING,
        mode=mode,
        gas=False,
    )
    result = plan(dataset, scenario)
    assert result.status == "ok", result.findings
    _conserved(result)
    assert {"pool_copper_enr_1", "liquid_purifier_copper_enr_1"} <= _recipes(result)
    assert not _machines(result) & GAS_MACHINES
    assert result.items["item_copper_enr"].delivered == 6


def test_hetonite_with_gas_takes_the_smaller_gas_route(dataset: Dataset) -> None:
    scenario = Scenario(
        supply=dict(NATURAL),
        targets={"item_copper_enr": Fraction(6)},
        basement=WULING,
        mode=PlanMode.MACHINES,
    )
    result = plan(dataset, scenario)
    assert result.status == "ok", result.findings
    _conserved(result)
    assert {
        "liquid_purifier_gas_copper_enr_2",
        "liquid_transmuter_2_solid_copper_enr_1",
    } <= (_recipes(result))
    assert (
        result.machine_count
        < plan(dataset, scenario.model_copy(update={"gas": False})).machine_count
    )


@pytest.mark.parametrize(
    "item_id",
    [
        "item_liquid_xiranite",
        "item_liquid_copper_enr",
        "item_copper_enr",
        "item_copper_cmpt",
    ],
)
def test_gas_off_keeps_liquid_lines_makeable(dataset: Dataset, item_id: str) -> None:
    scenario = Scenario(
        supply={**NATURAL, "item_xiranite_powder": None},
        targets={item_id: "min"},
        basement=WULING,
        gas=False,
    )
    result = plan(dataset, scenario)
    assert result.status == "ok", result.findings
    assert result.items[item_id].delivered > 0
    assert not _machines(result) & GAS_MACHINES


def test_two_ores_feed_two_refiners(dataset: Dataset) -> None:
    scenario = Scenario(
        supply=dict(NATURAL),
        targets={"item_copper_cmpt": Fraction(30), "item_iron_cmpt": Fraction(30)},
        basement=WULING,
        mode=PlanMode.MACHINES,
    )
    result = plan(dataset, scenario)
    assert result.status == "ok", result.findings
    _conserved(result)
    copper = {n.target for n in result.nets if n.item_id == "item_copper_ore"}
    iron = {n.target for n in result.nets if n.item_id == "item_iron_ore"}
    assert copper == {"furnance_copper_nugget_1"}
    assert iron == {"furnance_iron_nugget_1"}
    makers = {u.machine_id for u in result.recipes if u.recipe_id in dataset.recipes}
    assert makers == {"furnance_1", "component_mc_1"}


def test_natural_resources_are_plenty_unless_the_player_says_otherwise(
    dataset: Dataset,
) -> None:
    """Water is a world resource (RES-01, RES-03): a line never synthesises it."""
    scenario = Scenario(
        supply={"item_copper_ore": None, "item_xiranite_powder": None},
        targets={"item_copper_cmpt": Fraction(30)},
        basement=WULING,
    )
    result = plan(dataset, scenario)
    assert result.status == "ok", result.findings
    makers = {u.machine_id for u in result.recipes if u.recipe_id in dataset.recipes}
    assert makers == {"furnance_1", "component_mc_1"}
    assert result.items["item_liquid_water"].supplied == 30
    assert not _machines(result) & GAS_MACHINES
    starved = plan(dataset, scenario.model_copy(update={"natural_default": "none"}))
    assert "item_liquid_water" not in starved.items or (
        starved.items["item_liquid_water"].supplied == 0
    )
    zone = Scenario(
        supply={"item_carbon_mtl": None},
        targets={"item_xiranite_powder": Fraction(30)},
        basement=WULING,
        recipe_overrides={"item_xiranite_powder": "xiranite_oven_xiranite_powder_2"},
    )
    assert plan(dataset, zone).status == "infeasible"
    with_gas = plan(dataset, zone.model_copy(update={"gas_default": "plenty"}))
    assert with_gas.status == "ok"
    assert with_gas.items["item_gas_inert"].supplied == 6


def test_gas_off_never_marks_a_liquid_line_product_as_gathered(
    dataset: Dataset,
) -> None:
    scenario = Scenario(
        supply=dict(NATURAL),
        targets={"item_copper_enr_cmpt": "min"},
        basement=WULING,
        gas=False,
    )
    needs = requirements(dataset, scenario)
    assert "item_copper_enr" not in needs.gathered
    assert "item_copper_enr" in needs.intermediates
    assert {"item_copper_ore", "item_liquid_acid", "item_iron_ore"} <= set(
        needs.natural
    )
    result = plan(dataset, scenario)
    assert result.status == "ok", result.findings
    assert result.items["item_copper_enr_cmpt"].delivered > 0


@pytest.mark.parametrize("mode", list(PlanMode))
@pytest.mark.parametrize(
    "targets",
    [
        {"item_copper_enr": Fraction(6)},
        {"item_copper_cmpt": Fraction(30), "item_copper_enr": Fraction(6)},
        {"item_liquid_xiranite_enr": Fraction(30)},
    ],
)
def test_allowing_gas_never_costs_more(
    dataset: Dataset, mode: PlanMode, targets: dict[str, Fraction]
) -> None:
    supply = {**NATURAL, "item_xiranite_powder": None}
    without = plan(
        dataset,
        Scenario(supply=supply, targets=targets, basement=WULING, mode=mode, gas=False),
    )
    with_gas = plan(
        dataset,
        Scenario(supply=supply, targets=targets, basement=WULING, mode=mode, gas=True),
    )
    assert without.status == "ok" and with_gas.status == "ok"
    _conserved(without)
    _conserved(with_gas)
    if mode is PlanMode.MACHINES:
        assert with_gas.machine_count <= without.machine_count
    if mode is PlanMode.AREA:
        assert with_gas.footprint_cells <= without.footprint_cells


def test_power_is_the_total_the_machines_draw(dataset: Dataset) -> None:
    """The plan lists the total requirement (PWR-05) and plans no generation."""
    scenario = Scenario(
        supply={"item_xiranite_powder": None, "item_liquid_water": None},
        targets={"item_liquid_xiranite": Fraction(300)},
        basement=WULING,
        mode=PlanMode.MACHINES,
        natural_default="none",
        recipe_overrides={"item_liquid_xiranite": "pool_liquid_liquid_xiranite_1"},
    )
    result = plan(dataset, scenario)
    assert result.status == "ok", result.findings
    crucibles = sum(u.machines for u in result.recipes if u.machine_id == "mix_pool_1")
    assert crucibles == 10
    assert result.power == 10 * dataset.machines["mix_pool_1"].power == 500
    assert all(dataset.machines[u.machine_id].modes for u in result.recipes)
    assert "item_originium_ore" not in result.items
    power_notes = [f for f in result.findings if f.rule == "plan.power"]
    assert len(power_notes) == 1 and power_notes[0].severity == "info"
    assert "500" in power_notes[0].message


def test_event_recipes_are_not_planned(dataset: Dataset) -> None:
    """Limited-time recipes (RCP-06) are off unless the scenario allows events."""
    scenario = Scenario(
        supply={"item_xiranite_powder": None},
        targets={"item_activity_xiranite_nugget": Fraction(30)},
        basement=WULING,
    )
    result = plan(dataset, scenario)
    assert result.status == "infeasible"
    assert any(f.rule == "plan.unsupplied" for f in result.findings)
    allowed = plan(dataset, scenario.model_copy(update={"events": True}))
    assert allowed.status == "ok"
    assert "furnance_activity_xiranite_nugget_1" in _recipes(allowed)
