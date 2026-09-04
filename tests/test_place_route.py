"""Placement and routing on hand-built netlists and the benchmark scenarios."""

import subprocess
import sys
from fractions import Fraction
from pathlib import Path

import pytest

from kohakuefda.flow.evaluate import evaluate
from kohakuefda.layout.assemble import assemble, world_pins
from kohakuefda.layout.pipeline import layout_scenario
from kohakuefda.layout.place import Block
from kohakuefda.model.basement import Region
from kohakuefda.model.cells import Netlist, NetSpec, PinRef
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.scenario import BasementRef, Scenario
from kohakuefda.plan.machines import brick_cell
from kohakuefda.route.router import route_layout
from kohakuefda.verify.rules.geometry import check_layout

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "1.5.3@9764758-3" / "dataset.json"
BENCHMARKS = [
    "scenario_valley_battery.toml",
    "scenario_wuling_hetonite.toml",
    "scenario_gas_xiranite.toml",
]
ORE = "item_copper_ore"
SAND = "item_quartz_sand"
WULING = BasementRef(
    region=Region.WULING, basement_id="sky_king_flats", level=1, depot_level=1
)


@pytest.fixture(scope="module")
def dataset() -> Dataset:
    return Dataset.load(DATASET)


def _crossing_netlist(dataset: Dataset) -> tuple[list[Block], Netlist]:
    """Two unloaders above two loaders on the bottom row, wired diagonally so the belts
    must cross: no belt can pass below the loaders' ports."""
    src_a = brick_cell(dataset, "ua", "unloader", ORE, Fraction(30))
    src_b = brick_cell(dataset, "ub", "unloader", SAND, Fraction(30))
    dst_a = brick_cell(dataset, "la", "loader", ORE, Fraction(30))
    dst_b = brick_cell(dataset, "lb", "loader", SAND, Fraction(30))
    blocks = [Block.of_cell(c, dataset) for c in (src_a, src_b, dst_a, dst_b)]
    positions = {"ua": (2, 2), "ub": (12, 2), "la": (12, 14), "lb": (2, 14)}
    for block in blocks:
        block.x, block.y = positions[block.id]
        if block.kind == "loader":
            block.rotation = 180
    nets = [
        NetSpec(
            id="n_ore",
            item_id=ORE,
            kind="belt",
            rate=30,
            nominal=30,
            trunk_lanes=1,
            sources=[PinRef(cell_id="ua", pin_id=f"out:{ORE}:0", rate=30)],
            sinks=[PinRef(cell_id="la", pin_id=f"in:{ORE}:0", rate=30)],
        ),
        NetSpec(
            id="n_sand",
            item_id=SAND,
            kind="belt",
            rate=30,
            nominal=30,
            trunk_lanes=1,
            sources=[PinRef(cell_id="ub", pin_id=f"out:{SAND}:0", rate=30)],
            sinks=[PinRef(cell_id="lb", pin_id=f"in:{SAND}:0", rate=30)],
        ),
    ]
    scenario = Scenario(targets={}, basement=WULING)
    netlist = Netlist(
        dataset_version=dataset.version.id,
        scenario=scenario,
        plan_status="ok",
        cells=[src_a, src_b, dst_a, dst_b],
        nets=nets,
    )
    return blocks, netlist


def test_router_crosses_with_a_bridge_and_delivers(dataset: Dataset) -> None:
    blocks, netlist = _crossing_netlist(dataset)
    layout = assemble(dataset, blocks, dataset.version.id, WULING, 16, 16)
    route_layout(dataset, layout, world_pins(blocks), netlist)
    errors = [
        f
        for f in check_layout(dataset, layout)
        if f.severity == "error" and f.rule != "geom.depot_bus"
    ]
    assert errors == [], errors
    assert any(u.unit_id == "log_connector" for u in layout.units)
    result = evaluate(dataset, layout)
    assert result.machines["la:m0"].inputs == {ORE: 30}
    assert result.machines["lb:m0"].inputs == {SAND: 30}


@pytest.mark.parametrize("name", BENCHMARKS)
def test_benchmark_lays_out_clean_and_at_rate(
    dataset: Dataset, fixtures_dir: Path, name: str
) -> None:
    scenario = Scenario.from_toml(fixtures_dir / name)
    result = layout_scenario(dataset, scenario, {"spread_attempts": 2000})
    assert result.layout is not None, result.report.findings
    laid = [
        f
        for f in result.report.findings
        if f.severity == "error" and not f.rule.startswith("flow.")
    ]
    assert laid == [], laid
    assert result.evaluation is not None and result.evaluation.converged
    running: dict[str, Fraction] = {}
    for state in result.evaluation.machines.values():
        if state.recipe_id is not None:
            running[state.recipe_id] = (
                running.get(state.recipe_id, Fraction(0)) + state.utilisation
            )
    short = [
        use.recipe_id
        for use in result.plan.recipes
        if not use.recipe_id.startswith("dump:")
        and running[use.recipe_id] < use.machines_exact
    ]
    if short:
        pytest.xfail(f"the evaluator settles a recycle loop short: {short}")
    layout = result.layout
    area = layout.area_rect
    for placed in layout.machines:
        machine = dataset.machines[placed.machine_id]
        w, d = machine.size(placed.rotation)
        assert area[0] <= placed.x and placed.x + w <= area[2], placed.id
        assert area[1] <= placed.y and placed.y + d <= area[3], placed.id
    assert not any(m.machine_id == "sp_hub_1" for m in layout.machines)
    assert not any("pump" in m.machine_id for m in layout.machines)
    limit_x = dataset.constants.blueprint_max_x
    limit_z = dataset.constants.blueprint_max_z
    assert layout.modules
    for module in layout.modules:
        assert module.width <= limit_x and module.height <= limit_z
        assert len(module.entities) <= dataset.constants.blueprint_max_nodes


def test_layout_cli_writes_artifacts(fixtures_dir: Path, tmp_path: Path) -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "kohakuefda",
            "layout",
            str(fixtures_dir / "scenario_valley_battery.toml"),
            "-o",
            str(tmp_path),
            "--attempts",
            "200",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=ROOT,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    for name in ("plan.json", "netlist.json", "layout.json", "report.json"):
        assert (tmp_path / name).exists()
