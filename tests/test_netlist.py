"""Netlists carry the plan's rates over one cell per machine; bus parts, bricks and zones are
separate cells bound by groups; the CLI runs."""

import subprocess
import sys
from fractions import Fraction
from pathlib import Path

import pytest

from kohakuefda.layout.depot_via import (
    BUS_PORT,
    BUS_SECTION,
    chain_capacity,
    sections_needed,
)
from kohakuefda.model.cells import Netlist
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.scenario import Scenario
from kohakuefda.plan.machines import CORE, lane_groups
from kohakuefda.plan.netlist import build_netlist
from kohakuefda.plan.planner import plan

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "1.5.3@9764758-3" / "dataset.json"
BENCHMARKS = [
    "scenario_valley_battery.toml",
    "scenario_basic.toml",
    "scenario_gas_xiranite.toml",
]


@pytest.fixture(scope="module")
def dataset() -> Dataset:
    return Dataset.load(DATASET)


@pytest.mark.parametrize("name", BENCHMARKS)
def test_benchmark_netlist_matches_plan(
    dataset: Dataset, fixtures_dir: Path, name: str
) -> None:
    scenario = Scenario.from_toml(fixtures_dir / name)
    result = plan(dataset, scenario)
    assert result.status == "ok", result.findings
    netlist = build_netlist(dataset, scenario, result)
    assert netlist.errors == [], netlist.errors
    for net in netlist.nets:
        balance = result.items[net.item_id]
        assert net.rate == balance.produced + balance.supplied
        assert sum((r.rate for r in net.sinks), Fraction(0)) == net.rate
        assert sum((r.rate for r in net.sources), Fraction(0)) == net.rate
        assert net.nominal >= net.rate
    for use in result.recipes:
        if use.recipe_id.startswith("dump:"):
            continue
        machines = [
            m for c in netlist.cells for m in c.machines if m.recipe_id == use.recipe_id
        ]
        assert len(machines) == use.machines, use.recipe_id
    for cell in netlist.cells:
        assert len(cell.machines) == (0 if cell.kind == "entry" else 1), cell.id
        assert cell.machines == [] or (cell.machines[0].x, cell.machines[0].y) == (0, 0)
        for pin in cell.pins:
            assert pin.alternatives, (cell.id, pin.id)
            assert (pin.cell, pin.edge) in {(a.cell, a.edge) for a in pin.alternatives}
    for zone in (c for c in netlist.cells if c.kind == "zone"):
        assert (zone.width, zone.height) == (3, 3)
        assert zone.machines[0].machine_id == "vaporizer_1"
        assert zone.group and zone.group.startswith("zone")
    assert not [c for c in netlist.cells if c.kind == "core"]


def test_solids_enter_through_bus_parts_and_bricks_in_wuling(
    dataset: Dataset, fixtures_dir: Path
) -> None:
    scenario = Scenario.from_toml(fixtures_dir / "scenario_basic.toml")
    netlist = build_netlist(dataset, scenario, plan(dataset, scenario))
    parts = [c for c in netlist.cells if c.kind == "depot"]
    bricks = [c for c in netlist.cells if c.kind in ("unloader", "loader")]
    assert parts and bricks
    assert [c.machine_id for c in parts].count(BUS_PORT) == 1
    assert all(c.machine_id in (BUS_PORT, BUS_SECTION) for c in parts)
    assert all(
        c.group == "bus" and c.constraint == "free" and not c.pins for c in parts
    )
    assert all(c.group == "bus" and c.constraint == "free" for c in bricks)
    assert all(len(c.pins) == 1 and c.pins[0].kind == "belt" for c in bricks)
    assert all(len(c.machines) == 1 for c in parts + bricks)
    sections = sum(1 for c in parts if c.machine_id == BUS_SECTION)
    assert sections == sections_needed(len(bricks))
    assert chain_capacity(1, sections) >= len(bricks)
    assert any(f.rule == "netlist.bus" for f in netlist.findings)


def test_chain_capacity_and_lane_packing() -> None:
    assert chain_capacity(1, 0) == 4 and chain_capacity(1, 1) == 10
    assert chain_capacity(1, 2) == 14 and chain_capacity(2, 1) == 12
    assert chain_capacity(0, 0) == 0
    assert sections_needed(4) == 0 and sections_needed(5) == 1
    assert sections_needed(11) == 2 and sections_needed(14) == 2
    lanes = lane_groups(
        [Fraction(10), Fraction(10), Fraction(10), Fraction(5)], Fraction(30)
    )
    assert lanes == [Fraction(30), Fraction(5)]


def test_fluids_enter_at_the_border_and_zones_group_their_machines(
    dataset: Dataset, fixtures_dir: Path
) -> None:
    scenario = Scenario.from_toml(fixtures_dir / "scenario_gas_xiranite.toml")
    result = plan(dataset, scenario)
    assert result.zones == {"stable": 1}
    netlist = build_netlist(dataset, scenario, result)
    entries = [c for c in netlist.cells if c.kind == "entry"]
    assert entries and all(c.constraint == "edge" for c in entries)
    assert {c.pins[0].item_id for c in entries} == {
        "item_gas_inert",
        "item_liquid_water",
    }
    assert all(
        c.pins[0].direction == "out" and c.pins[0].kind == "pipe" for c in entries
    )
    assert not any(c.kind == "pump" for c in netlist.cells)
    zones = [c for c in netlist.cells if c.kind == "zone"]
    assert zones and all(z.env == "stable" for z in zones)
    ovens = [
        c
        for c in netlist.cells
        if c.kind == "recipe" and c.recipe_id == "xiranite_oven_xiranite_powder_2"
    ]
    assert len(ovens) == sum(
        u.machines
        for u in result.recipes
        if u.recipe_id == "xiranite_oven_xiranite_powder_2"
    )
    assert all(o.env == "stable" and o.group in {z.group for z in zones} for o in ovens)
    assert all(any(p.id.startswith("in:item_gas_inert") for p in z.pins) for z in zones)
    gas = next(n for n in netlist.nets if n.item_id == "item_gas_inert")
    assert gas.rate == 6 * len(zones) and gas.kind == "pipe"
    assert any(f.rule == "netlist.zones" for f in netlist.findings)
    assert any(f.rule == "netlist.entries" for f in netlist.findings)


def test_the_core_is_left_out_unless_the_scenario_asks_for_it(
    dataset: Dataset, fixtures_dir: Path
) -> None:
    scenario = Scenario.from_toml(fixtures_dir / "scenario_basic.toml")
    result = plan(dataset, scenario)
    without = build_netlist(dataset, scenario, result)
    assert not [c for c in without.cells if c.kind == "core"]
    assert any(c.kind == "depot" for c in without.cells)
    parked = build_netlist(dataset, scenario.model_copy(update={"core": True}), result)
    core = next(c for c in parked.cells if c.kind == "core")
    assert core.constraint == "park" and core.pins == [] and core.machine_id == CORE
    wired = build_netlist(
        dataset, scenario.model_copy(update={"depot": "core"}), result
    )
    core = next(c for c in wired.cells if c.kind == "core")
    assert core.constraint == "free" and len(core.pins_of("out")) <= 6
    assert core.pins


def test_valley_bricks_bind_to_bus_slots(dataset: Dataset) -> None:
    scenario = Scenario.from_toml_text(
        "gas = false\n"
        "[supply]\n"
        "item_originium_ore = 'unlimited'\n"
        "item_quartz_sand = 'unlimited'\n"
        "item_iron_ore = 'unlimited'\n"
        "[targets]\n"
        "item_originium_powder = 90\n"
        "item_quartz_glass = 90\n"
        "item_iron_nugget = 90\n"
        "[basement]\n"
        "region = 'valley4'\n"
        "basement_id = 'the_hub'\n"
        "level = 2\n"
        "depot_level = 3\n"
    )
    result = plan(dataset, scenario)
    assert result.status == "ok", result.findings
    netlist = build_netlist(dataset, scenario, result)
    bricks = [c for c in netlist.cells if c.kind in ("unloader", "loader")]
    assert len(bricks) == 18 and all(c.constraint == "slot" for c in bricks)
    assert sum(1 for c in bricks if c.kind == "unloader") == 9
    assert not any(c.kind == "depot" for c in netlist.cells)
    assert netlist.errors == []
    wired = build_netlist(
        dataset, scenario.model_copy(update={"depot": "core"}), result
    )
    bricks = [c for c in wired.cells if c.kind in ("unloader", "loader")]
    assert len(bricks) == 3 and all(c.kind == "unloader" for c in bricks)
    assert wired.errors == []


def test_netlist_round_trips_and_cli_runs(fixtures_dir: Path, tmp_path: Path) -> None:
    out = tmp_path / "netlist.json"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "kohakuefda",
            "netlist",
            str(fixtures_dir / "scenario_valley_battery.toml"),
            "-o",
            str(out),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=ROOT,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    loaded = Netlist.load(out)
    assert loaded.cells and loaded.nets
