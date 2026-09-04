"""Pinned facts about the shipped dataset, checked against the game and the wiki."""

from fractions import Fraction
from pathlib import Path

import pytest

from kohakuefda.data.normalize.ports import on_edge
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.geometry import Edge
from kohakuefda.model.items import Phase
from kohakuefda.model.machines import PortDir, PortType

DATASET = (
    Path(__file__).resolve().parents[1] / "data" / "1.5.3@9764758-3" / "dataset.json"
)


@pytest.fixture(scope="module")
def dataset() -> Dataset:
    return Dataset.load(DATASET)


def test_version_and_counts(dataset: Dataset) -> None:
    assert dataset.version.game_version == "1.5.3"
    assert dataset.version.hotfix == "9764758-3"
    assert len(dataset.recipes) == 317
    assert len(dataset.items) == 564
    assert len(dataset.machines) >= 60


def test_logistics_constants(dataset: Dataset) -> None:
    c = dataset.constants
    assert c.belt_per_min == Fraction(30)
    assert c.pipe_per_min == Fraction(120)
    assert (c.belt_run_max, c.pipe_run_max, c.conduit_link_max) == (110, 80, 300)
    assert c.fluid_router_limit == 128
    assert (c.blueprint_max_x, c.blueprint_max_z, c.blueprint_max_nodes) == (
        50,
        50,
        160,
    )
    assert c.control_port_limit == {"domain_1": 50, "domain_2": 70}
    assert c.core_power == 200


def test_refining_unit_geometry_and_names(dataset: Dataset) -> None:
    m = dataset.machines["furnance_1"]
    assert (m.width, m.depth, m.height, m.power, m.capacity_cost) == (3, 3, 4, 5, 2)
    assert [x.name for x in m.modes] == ["normal", "liquid"]
    belt_in = m.ports_of(PortDir.IN, PortType.BELT)
    belt_out = m.ports_of(PortDir.OUT, PortType.BELT)
    assert [(p.x, p.y, p.edge) for p in belt_in] == [
        (0, 0, Edge.N),
        (1, 0, Edge.N),
        (2, 0, Edge.N),
    ]
    assert [(p.x, p.y, p.edge) for p in belt_out] == [
        (0, 2, Edge.S),
        (1, 2, Edge.S),
        (2, 2, Edge.S),
    ]
    (pipe_in,) = m.ports_of(PortDir.IN, PortType.PIPE)
    (pipe_out,) = m.ports_of(PortDir.OUT, PortType.PIPE)
    assert (pipe_in.edge, pipe_in.layer, pipe_out.edge, pipe_out.layer) == (
        Edge.W,
        1,
        Edge.E,
        1,
    )
    assert (m.names.en, m.names.zh_tw, m.names.zh_cn) == (
        "Refining Unit",
        "精煉爐",
        "精炼炉",
    )


def test_filling_unit_and_hub_ports(dataset: Dataset) -> None:
    f = dataset.machines["filling_powder_mc_1"]
    assert (f.width, f.depth) == (6, 4)
    assert len(f.ports_of(PortDir.IN, PortType.BELT)) == 6
    assert len(f.ports_of(PortDir.IN, PortType.PIPE)) == 1
    assert len(f.ports_of(PortDir.OUT, PortType.BELT)) == 6
    hub = dataset.machines["sp_hub_1"]
    assert (hub.width, hub.depth) == (9, 9)
    ins = hub.ports_of(PortDir.IN)
    outs = hub.ports_of(PortDir.OUT)
    assert len(ins) == 14 and {p.edge for p in ins} == {Edge.N, Edge.S}
    assert len(outs) == 6 and {p.edge for p in outs} == {Edge.E, Edge.W}


def test_every_port_lies_on_its_edge(dataset: Dataset) -> None:
    for machine in dataset.machines.values():
        for port in machine.ports:
            assert on_edge(port.x, port.y, machine.width, machine.depth, port.edge), (
                machine.id,
                port,
            )
            assert port.layer == (1 if port.type is PortType.PIPE else 0)


def test_crucible_recipe_bindings(dataset: Dataset) -> None:
    r = dataset.recipes["pool_copper_enr_1"]
    assert r.machine_id == "mix_pool_1" and r.mode == "liquid"
    assert r.seconds == Fraction(2) and r.crafts_per_minute == Fraction(30)
    assert [(s.item_id, s.count) for s in r.inputs] == [
        ("item_liquid_copper_enr", 2),
        ("item_iron_powder", 1),
    ]
    assert r.output_rate("item_liquid_sewage") == Fraction(30)
    assert dataset.output_ports(r, "item_liquid_sewage") == [3]
    assert dataset.output_ports(r, "item_copper_enr") == [0, 1]
    assert dataset.input_ports(r, "item_liquid_copper_enr") == [2, 3]
    assert dataset.input_ports(r, "item_iron_powder") == [0, 1]
    assert r.input_rate("item_liquid_copper_enr") == Fraction(60)


def test_recipes_reference_known_ids_and_modes(dataset: Dataset) -> None:
    for recipe in dataset.recipes.values():
        machine = dataset.machines[recipe.machine_id]
        assert recipe.mode in {m.name for m in machine.modes}, recipe.id
        for stack in recipe.inputs + recipe.outputs:
            assert stack.item_id in dataset.items, (recipe.id, stack.item_id)


def test_item_phases_and_names(dataset: Dataset) -> None:
    water = dataset.items["item_liquid_water"]
    assert water.phase is Phase.LIQUID and not water.storable
    assert (water.names.en, water.names.zh_tw) == ("Clean Water", "清水")
    ore = dataset.items["item_originium_ore"]
    assert ore.phase is Phase.SOLID and ore.storable
    assert {i.phase for i in dataset.items.values()} == {
        Phase.SOLID,
        Phase.LIQUID,
        Phase.GAS,
    }


def test_logistics_units(dataset: Dataset) -> None:
    units = dataset.logistics
    assert units["grid_belt_01"].rate_per_min == Fraction(30)
    assert units["log_pipe_01"].rate_per_min == Fraction(120)
    assert units["log_splitter"].width == 1 and len(units["log_splitter"].ports) == 4
    assert units["log_pipe_splitter"].height == 4
    assert units["udpipe_loader_2"].rate_per_min == Fraction(240)
    assert units["udpipe_loader_1"].capacity == 500


def test_basements_present(dataset: Dataset) -> None:
    sky = dataset.basements["sky_king_flats"]
    assert sky.square(1) == (30, 30) and sky.square(3) == (50, 50)
    assert sky.depot.kind == "laid"
    assert dataset.basements["infra_station"].depot.kind == "fixed"
    assert dataset.basements["infra_station"].square(1) == (24, 27)
