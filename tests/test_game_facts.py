"""Mechanics the layout and the planner rely on, pinned against the wiki and the community
calculators: pylons, the core, plots, activation, zones, dumps, source rates."""

from fractions import Fraction
from pathlib import Path

import pytest

from kohakuefda.model.dataset import Dataset
from kohakuefda.model.machines import PortDir
from kohakuefda.model.sinks import (
    GAS_PUMP,
    LIQUID_PUMP,
    SOURCE_RATES,
    ZONE_GAS_PER_MIN,
    ZONE_MACHINE,
    ZONE_SIDE,
)

DATASET = (
    Path(__file__).resolve().parents[1] / "data" / "1.5.3@9764758-3" / "dataset.json"
)


@pytest.fixture(scope="module")
def dataset() -> Dataset:
    return Dataset.load(DATASET)


def test_pylon_and_core_footprints(dataset: Dataset) -> None:
    pylon = dataset.machines["power_diffuser_1"]
    assert (pylon.width, pylon.depth, pylon.power, pylon.needs_power) == (2, 2, 0, True)
    assert pylon.ports == []
    core = dataset.machines["sp_hub_1"]
    assert (core.width, core.depth) == (9, 9)
    assert len(core.ports_of(PortDir.IN)) == 14 and len(core.ports_of(PortDir.OUT)) == 6
    assert dataset.constants.core_power == 200


def test_pylon_coverage_is_recorded(dataset: Dataset) -> None:
    """Electric Pylon: reach 5 around its 2×2 (COV-01), 30 m cable (COV-06); relays 80 m (COV-05)."""
    pylon = dataset.pylons["power_diffuser_1"]
    assert (pylon.reach, pylon.auto_connect_length, pylon.covers) == (5, 30, True)
    assert pylon.coverage(10, 20, 2, 2) == (5, 15, 17, 27)
    assert dataset.pylons["power_diffuser_2"].auto_connect is True
    relay = dataset.pylons["power_pole_2"]
    assert (relay.reach, relay.auto_connect_length, relay.covers) == (2, 80, False)
    assert dataset.pylons["power_pole_3"].auto_connect_length == 80


def test_core_areas_and_depot_buses(dataset: Dataset) -> None:
    """Squares per expansion (REG-04), the ring (REG-03), fixed Valley IV buses (DEP-12), Wuling limits (DEP-10)."""
    hub = dataset.basements["the_hub"]
    assert [hub.square(lv) for lv in (1, 2, 3)] == [(32, 32), (52, 52), (70, 70)]
    assert [dataset.basements["wuling_city"].square(lv) for lv in (1, 2, 3)] == [
        (40, 40),
        (60, 60),
        (80, 80),
    ]
    assert dataset.basements["refugee_camp"].square(1) == (24, 27)
    assert (hub.ring, dataset.basements["sky_king_flats"].ring) == (5, 10)
    assert hub.depot.kind == "fixed" and hub.depot.positions_known
    assert hub.depot.port is not None and hub.depot.port.rect == (-4, -4, 0, 0)
    assert [len(hub.depot.segments(lv)) for lv in (1, 3, 6)] == [3, 9, 18]
    outpost = dataset.basements["infra_station"].depot
    assert [len(outpost.segments(lv)) for lv in (1, 2, 3)] == [2, 4, 5]
    assert all(s.y == -4 and s.depth == 4 for s in outpost.segments(3))
    wuling = dataset.basements["sky_king_flats"].depot
    assert wuling.kind == "laid"
    assert (wuling.sections_by_level[4], wuling.ports_by_level[4]) == (12, 2)


def test_planting_unit_needs_no_plot(dataset: Dataset) -> None:
    planter = dataset.machines["planter_1"]
    assert (planter.width, planter.depth, planter.power) == (5, 5, 20)
    recipes = dataset.recipes_of("planter_1")
    assert len(recipes) == 6 and all(r.seconds == Fraction(2) for r in recipes)
    plots = [m for m in dataset.machines.values() if m.id.startswith("soil_")]
    assert len(plots) == 14
    for plot in plots:
        assert (plot.width, plot.depth, plot.ports, plot.needs_power) == (
            4,
            4,
            [],
            False,
        )
        assert dataset.recipes_of(plot.id) == []
    assert dataset.constants.farmland_limit == 24


def test_activation_zone_and_transmuters(dataset: Dataset) -> None:
    liquid = dataset.activations["transmuter_1"]
    gas = dataset.activations["transmuter_2"]
    assert (liquid.item_id, liquid.min_rate) == ("item_liquid_xiranite", Fraction(6))
    assert (gas.item_id, gas.min_rate) == ("item_gas_xiranite", Fraction(6))
    assert ZONE_GAS_PER_MIN == Fraction(6) and ZONE_SIDE == 13
    zone = dataset.machines[ZONE_MACHINE]
    assert (zone.width, zone.depth, zone.power) == (3, 3, 0)
    assert set(dataset.env_gases) == {"stable", "humid", "acrid", "xiranite"}


def test_dumps_and_sources(dataset: Dataset) -> None:
    cleaner = dataset.dumps["liquid_cleaner_1"]
    assert (cleaner.rate_per_machine, cleaner.fixed) == (Fraction(30), False)
    assert "item_liquid_sewage" in cleaner.items
    inlet = dataset.dumps["liquid_clean_gate_1"]
    assert (inlet.rate_per_machine, inlet.fixed, inlet.items) == (
        Fraction(120),
        True,
        ["item_liquid_sewage"],
    )
    assert SOURCE_RATES["unloader_1"] == Fraction(30)
    assert SOURCE_RATES[LIQUID_PUMP] == Fraction(60)
    assert SOURCE_RATES[GAS_PUMP] == Fraction(20)
    assert {"item_liquid_water", "item_liquid_acid", "item_gas_inert"} <= set(
        dataset.resources
    )
