"""A unit as its own problem: rim sides from the nets, the tile problem, the rim anchors."""

from pathlib import Path

import pytest

from kohakuefda.layout.settings import router_of
from kohakuefda.layout.tiles import lay_out_tile, pinned_extent, text_map, tile_box
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.scenario import Scenario
from kohakuefda.physics.boundaries import RIM, rim_anchors
from kohakuefda.physics.fabric import area_rect
from kohakuefda.physics.facts import facts
from kohakuefda.plan.netlist import build_netlist
from kohakuefda.plan.planner import plan
from kohakuefda.synth import problem_of
from kohakuefda.synth.hierarchy import hierarchical_of, instance_id
from kohakuefda.synth.tiles import port_sides, tile_problem, with_macros
from kohakulayout.engine import Budget, Context

ROOT = Path(__file__).resolve().parent.parent
DATASET = ROOT / "data" / "1.5.3@9764758-3" / "dataset.json"
FIXTURES = ROOT / "tests" / "fixtures"


@pytest.fixture(scope="module")
def hier(dataset_path: Path = DATASET):
    dataset = Dataset.load(dataset_path)
    scenario = Scenario.from_toml(FIXTURES / "scenario_dense_valley18.toml")
    netlist = build_netlist(dataset, scenario, plan(dataset, scenario))
    return hierarchical_of(netlist, problem_of(dataset, netlist).netlist)


def test_port_sides_follow_the_flow(hier) -> None:
    line = instance_id("tools_proc_battery_3_1")
    moss = instance_id("grinder_plant_moss_powder_3_1")
    sides = port_sides(hier, line)
    by_item: dict[str, set[str]] = {}
    for port in hier.modules[line].ports:
        item = port.inner.pin.split("__")[1]
        by_item.setdefault(item, set()).add(sides[port.id])
    assert by_item == {
        "item_iron_powder": {"N"},
        "item_originium_powder": {"N"},
        "item_plant_moss_powder_3": {"N"},
        "item_proc_battery_3": {"S"},
    }
    assert set(port_sides(hier, moss).values()) == {"S"}
    assert {t for t in hier.modules} == {
        line,
        moss,
        instance_id("grinder_iron_powder_1"),
        instance_id("grinder_originium_powder_1"),
    }


def test_the_tile_problem_pins_port_cells_to_the_rim_and_checks_clean(hier) -> None:
    moss = instance_id("grinder_plant_moss_powder_3_1")
    problem = tile_problem(hier, moss, tile_box(hier, moss))
    assert problem.check() == []
    assert len(problem.netlist.cells) == 4
    rims = {k: c for k, c in problem.netlist.cells.items() if c.constraint.kind == RIM}
    assert len(rims) == 1
    ((cell_id, cell),) = rims.items()
    assert facts(cell)["rims"] == [
        f"S:out__item_plant_moss_powder_3__{n}" for n in range(3)
    ]
    assert pinned_extent(problem) == (None, None)
    ctx = Context(problem, router=router_of(), budget=Budget(units=10))
    anchors = list(rim_anchors(ctx.world, cell))
    x0, _, x1, y1 = area_rect(problem.fabric)
    assert anchors and all(y + 3 == y1 and x0 <= x < x1 for x, y, _ in anchors)
    assert all(a in set(ctx.world.anchor_rows(cell_id)) for a in anchors)


def test_a_tile_lays_out_once_into_a_macro_the_hierarchy_places(hier) -> None:
    moss = instance_id("grinder_plant_moss_powder_3_1")
    result = lay_out_tile(hier, moss, seeds=(0,), units=3000)
    assert result.assessment.complete and result.assessment.valid
    footprint = result.macro.footprint
    assert footprint is not None and {p.side for p in footprint.ports} == {"S"}
    assert len(footprint.ports) == 3
    assert not result.macro.layout.units
    fragment = set()
    for placement in result.macro.layout.placements.values():
        fragment.add((placement.x, placement.y))
    assert min(x for x, _ in fragment) >= 0 and min(y for _, y in fragment) >= 0
    found = result.complexity
    assert found.belt_cells > 0 and found.bridges == 0
    rows = text_map(result.problem, result.macro.layout, footprint).splitlines()
    assert len(rows) == footprint.height + 2 and "G" in "".join(rows)
    placed = with_macros(hier, {moss: result.macro})
    assert placed.check() == []
    instances = [c for c in placed.cells.values() if c.macro == result.macro.id]
    assert len(instances) == 5 and all(c.module is None for c in instances)
    assert placed.footprint_for(instances[0].id) is footprint
    flat = placed.flatten()
    assert len(flat.cells) == len(hier.flatten().cells)
