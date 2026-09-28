"""Repeat units from the plan: tiles by integral grouping, cell membership, the report's unit terms."""

from collections import Counter
from pathlib import Path

import pytest

from kohakuefda.model.dataset import Dataset
from kohakuefda.model.scenario import Scenario
from kohakuefda.plan.netlist import build_netlist
from kohakuefda.plan.planner import plan
from kohakuefda.plan.units import assign_units, extract, unit_name
from kohakuefda.synth import problem_of
from kohakuefda.synth.hierarchy import hierarchical_of, instance_id
from kohakuefda.synth.problem import lanes_of
from kohakuefda.verify.complexity import Complexity, complexity_text, with_units

ROOT = Path(__file__).resolve().parent.parent
DATASET = ROOT / "data" / "1.5.3@9764758-3" / "dataset.json"
FIXTURES = ROOT / "tests" / "fixtures"


@pytest.fixture(scope="module")
def dataset() -> Dataset:
    return Dataset.load(DATASET)


def _plan(dataset: Dataset, name: str):
    scenario = Scenario.from_toml(FIXTURES / f"scenario_{name}.toml")
    return scenario, plan(dataset, scenario)


def test_valley18_is_three_lines_and_five_moss_tiles(dataset: Dataset) -> None:
    _, result = _plan(dataset, "dense_valley18")
    hierarchy = extract(dataset, result)
    top = {t.id: t for t in hierarchy.top}
    assert set(top) == {
        "tools_proc_battery_3_1",
        "grinder_plant_moss_powder_3_1",
        "grinder_iron_powder_1",
        "grinder_originium_powder_1",
    }
    line, moss = top["tools_proc_battery_3_1"], top["grinder_plant_moss_powder_3_1"]
    assert line.copies == 3 and hierarchy.machines(line.id) == 10
    assert line.members == {
        "component_iron_enr_cmpt_1": 2,
        "thickener_originium_enr_powder_1": 3,
    }
    assert hierarchy.tile("thickener_iron_enr_powder_1").members == {}
    assert top["grinder_iron_powder_1"].copies == 12
    assert top["grinder_iron_powder_1"].members == {"furnance_iron_nugget_1": 1}
    assert top["grinder_originium_powder_1"].copies == 18
    assert moss.copies == 5 and hierarchy.machines(moss.id) == 4
    assert moss.members == {"planter_plant_moss_3_1+seedcollector_plant_moss_3_1": 1}
    loop = hierarchy.tile("planter_plant_moss_3_1+seedcollector_plant_moss_3_1")
    assert loop.per_copy == {
        "planter_plant_moss_3_1": 2,
        "seedcollector_plant_moss_3_1": 1,
    }
    total = sum(t.copies * hierarchy.machines(t.id) for t in hierarchy.top)
    assert total == sum(
        u.machines for u in result.recipes if not u.recipe_id.startswith("dump:")
    )
    between = {
        (f.item_id, f.source, f.sink) for f in hierarchy.flows if f.source and f.sink
    }
    assert between == {
        ("item_plant_moss_powder_3", moss.id, line.id),
        ("item_iron_powder", "grinder_iron_powder_1", line.id),
        ("item_originium_powder", "grinder_originium_powder_1", line.id),
    }
    assert {f.item_id for f in hierarchy.flows if not f.source} == {
        "item_iron_ore",
        "item_originium_ore",
    }


def test_liquids_bind_no_tile_and_cycles_share_copies(dataset: Dataset) -> None:
    _, result = _plan(dataset, "dense_wuling6")
    hierarchy = extract(dataset, result)
    assert len(hierarchy.top) == 12
    for tile in hierarchy.tiles:
        assert all(v > 0 for v in tile.per_copy.values())
        if tile.parent is not None:
            parent = hierarchy.tile(tile.parent)
            assert tile.copies == parent.copies * parent.members[tile.id]
    loop = hierarchy.tile(
        "grinder_plant_moss_powder_3_1+planter_plant_moss_3_1+seedcollector_plant_moss_3_1"
    )
    assert loop.copies == 1 and loop.per_copy == {
        "grinder_plant_moss_powder_3_1": 3,
        "planter_plant_moss_3_1": 5,
        "seedcollector_plant_moss_3_1": 3,
    }
    assert not any(
        "liquid" in f.item_id and f.source and f.sink for f in hierarchy.flows
    )


def test_cells_take_their_tile_and_copy_and_side_cells_follow(dataset: Dataset) -> None:
    scenario, result = _plan(dataset, "dense_valley18")
    netlist = build_netlist(dataset, scenario, result)
    units = Counter(c.unit for c in netlist.cells if c.kind == "recipe")
    assert units == {
        **{unit_name("tools_proc_battery_3_1", k): 10 for k in range(3)},
        **{unit_name("grinder_plant_moss_powder_3_1", k): 4 for k in range(5)},
        **{unit_name("grinder_iron_powder_1", k): 2 for k in range(12)},
        **{unit_name("grinder_originium_powder_1", k): 1 for k in range(18)},
    }
    assert all(c.unit is None for c in netlist.cells if c.kind != "recipe")
    scenario, result = _plan(dataset, "dense_wuling6")
    netlist = build_netlist(dataset, scenario, result)
    cells = {c.id: c for c in netlist.cells}
    outlets = [c for c in netlist.cells if c.kind == "outlet"]
    assert outlets
    followed = 0
    for outlet in outlets:
        consumer = cells[outlet.pins[0].net.rsplit("_", 1)[0]]
        assert outlet.unit in (None, consumer.unit)
        followed += outlet.unit == consumer.unit
    assert followed
    assign_units(extract(dataset, result), netlist.cells)
    assert Counter(c.unit for c in netlist.cells) == Counter(
        c.unit for c in build_netlist(dataset, scenario, result).cells
    )


def test_the_report_carries_the_units(dataset: Dataset) -> None:
    _, result = _plan(dataset, "dense_valley18")
    found = with_units(Complexity(), extract(dataset, result))
    assert (found.unit_types, found.unit_copies, found.global_nets) == (4, 38, 3)
    assert complexity_text(found).endswith("units=4x38 global=3")


def _signature(netlist):
    cells = Counter(
        (c.footprint, tuple((p.id, p.direction, p.carrier) for p in netlist.pins_of(k)))
        for k, c in netlist.cells.items()
    )
    nets = Counter(
        (
            n.carrier,
            n.rate,
            tuple(sorted((netlist.cells[r.cell].footprint, r.pin) for r in n.sources)),
            tuple(sorted((netlist.cells[r.cell].footprint, r.pin) for r in n.sinks)),
        )
        for n in netlist.nets.values()
    )
    return cells, nets


@pytest.mark.parametrize("name", ["basic", "dense_valley18", "gas_xiranite"])
def test_the_hierarchical_netlist_flattens_to_the_flat_one(
    dataset: Dataset, name: str
) -> None:
    scenario, result = _plan(dataset, name)
    netlist = build_netlist(dataset, scenario, result)
    flat = problem_of(dataset, netlist).netlist
    hier = hierarchical_of(netlist, flat)
    assert hier.check() == []
    assert hier.is_flat == (not any(c.unit for c in netlist.cells)) and flat.is_flat
    copies = Counter(c.unit.rsplit("#", 1)[0] for c in netlist.cells if c.unit)
    assert set(hier.modules) == {instance_id(t) for t in copies}
    assert _signature(hier.flatten()) == _signature(flat)
    for module in hier.modules.values():
        assert module.ports and all(
            p.inner.cell in module.body.cells for p in module.ports
        )
        assert all(
            r.cell in module.body.cells
            for n in module.body.nets.values()
            for r in (*n.sources, *n.sinks)
        )


def test_lanes_pair_the_pins_of_one_copy_first(dataset: Dataset) -> None:
    scenario, result = _plan(dataset, "dense_valley18")
    netlist = build_netlist(dataset, scenario, result)
    units = {c.id: c.unit for c in netlist.cells}
    moss = next(n for n in netlist.nets if n.item_id == "item_plant_moss_3")
    lanes = lanes_of(moss, units)
    assert lanes and all(units[s[0]] == units[t[0]] for s, t, _ in lanes)
    mixed = lanes_of(moss)
    assert any(units[s[0]] != units[t[0]] for s, t, _ in mixed)
