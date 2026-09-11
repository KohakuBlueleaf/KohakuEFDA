"""The layout stage on small hand-built netlists: what the game asks of a placed line.

Wired machines end close, routed and powered; outside inputs stand on the border and feed
their zone; bricks seat on a laid bus that stays one cluster, or take the fixed slots;
the parked core stays inside the area; a cancelled stage raises; the rules judge
hand-built layouts.
"""

from fractions import Fraction
from pathlib import Path

import pytest

from kohakuefda.layout.stages import StageError, layout_stage, params_of
from kohakuefda.model.basement import Region
from kohakuefda.model.cells import CellInstance, Netlist, NetSpec, PinRef
from kohakuefda.model.control import CancelledError
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.layout import Entry, Layout, Placed, Segment
from kohakuefda.model.scenario import BasementRef, Scenario
from kohakuefda.physics import carriers
from kohakuefda.physics.boundaries import ZONE_REACH, inside
from kohakuefda.plan.depot import BUS_PORT, BUS_SECTION, io_budget
from kohakuefda.plan.machines import (
    brick_cell,
    bus_part,
    core_cell,
    entry_cell,
    parked_core,
    recipe_cell,
    single_cell,
    zone_cell,
)
from kohakuefda.verify.evaluate import evaluate
from kohakuefda.verify.layout import check_layout

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "1.5.3@9764758-3" / "dataset.json"
WULING = BasementRef(
    region=Region.WULING, basement_id="sky_king_flats", level=1, depot_level=1
)
VALLEY = BasementRef(
    region=Region.VALLEY4, basement_id="infra_station", level=1, depot_level=2
)
ORE = "item_copper_ore"
NUGGET = "item_copper_nugget"
WATER = "item_liquid_water"
GAS = "item_gas_inert"
FAST = {
    "solver": "regional",
    "seconds": 0,
    "max_actions": 6000,
    "backend": "auto",
    "workers": 1,
    "frame_every": 1000,
}
PinKey = tuple[str, str]


@pytest.fixture(scope="module")
def dataset() -> Dataset:
    return Dataset.load(DATASET)


def _net(
    net_id: str,
    item_id: str,
    kind: str,
    sources: list[PinKey],
    sinks: list[PinKey],
    rate: int = 30,
) -> NetSpec:
    return NetSpec(
        id=net_id,
        item_id=item_id,
        kind=kind,
        rate=rate,
        nominal=rate,
        trunk_lanes=1,
        sources=[
            PinRef(cell_id=c, pin_id=p, rate=Fraction(rate, len(sources)))
            for c, p in sources
        ],
        sinks=[
            PinRef(cell_id=c, pin_id=p, rate=Fraction(rate, len(sinks)))
            for c, p in sinks
        ],
    )


def _netlist(
    dataset: Dataset,
    basement: BasementRef,
    cells: list[CellInstance],
    nets: list[NetSpec],
) -> Netlist:
    return Netlist(
        dataset_version=dataset.version.id,
        scenario=Scenario(targets={}, basement=basement),
        plan_status="ok",
        cells=cells,
        nets=nets,
    )


def _run(dataset: Dataset, netlist: Netlist, **params):
    return layout_stage(dataset, netlist, {**FAST, **params})


def _errors(dataset: Dataset, layout: Layout) -> list:
    return [f for f in check_layout(dataset, layout) if f.severity == "error"]


def _pin(cell: CellInstance, item_id: str) -> str:
    return next(p for p in cell.pins if p.item_id == item_id).id


def _furnace_pair(dataset: Dataset) -> Netlist:
    furnace = recipe_cell(dataset, "f", dataset.recipes["furnance_copper_nugget_1"])
    grinder = recipe_cell(dataset, "g", dataset.recipes["grinder_copper_powder_1"])
    nets = [
        _net(
            "n",
            NUGGET,
            "belt",
            [("f", _pin(furnace, NUGGET))],
            [("g", _pin(grinder, NUGGET))],
            15,
        )
    ]
    return _netlist(
        dataset, WULING, [furnace, grinder, parked_core(dataset, "core")], nets
    )


def test_wired_machines_end_close_routed_and_powered(dataset: Dataset) -> None:
    placement, layout = _run(dataset, _furnace_pair(dataset), seed=2)
    assert placement.findings == [] and _errors(dataset, layout) == []
    furnace, grinder = placement.block("f"), placement.block("g")
    assert abs(furnace.x - grinder.x) + abs(furnace.y - grinder.y) <= 12
    assert layout.segments and placement.terms["length"] <= 16
    assert placement.pylons and placement.terms["pylons"] >= 1
    assert evaluate(dataset, layout).converged


def test_the_parked_core_stays_inside_the_area_and_counts(dataset: Dataset) -> None:
    placement, layout = _run(dataset, _furnace_pair(dataset), seed=1)
    assert _errors(dataset, layout) == []
    core = next(m for m in layout.machines if m.machine_id == "sp_hub_1")
    rect = (core.x, core.y, core.x + 9, core.y + 9)
    assert inside(rect, layout.area_rect)
    for other in layout.machines:
        if other.id == core.id:
            continue
        w, d = dataset.machines[other.machine_id].size(other.rotation)
        box = (other.x, other.y, other.x + w, other.y + d)
        assert not (
            rect[0] < box[2]
            and box[0] < rect[2]
            and rect[1] < box[3]
            and box[1] < rect[3]
        ), other.id
    footprint = sum(
        dataset.machines[m.machine_id].width * dataset.machines[m.machine_id].depth
        for m in layout.machines
        if m.machine_id != "power_diffuser_1"
    )
    assert 9 * 9 < footprint <= placement.terms["area"]


def test_outside_inputs_sit_on_the_border_and_feed_the_zone(dataset: Dataset) -> None:
    oven = recipe_cell(dataset, "o", dataset.recipes["xiranite_oven_xiranite_powder_2"])
    oven.group = "zone0"
    unit = zone_cell(dataset, "z", "stable", "zone0")
    water = entry_cell("ew", WATER, Fraction(30))
    gas = entry_cell("eg", GAS, Fraction(6))
    nets = [
        _net(
            "w",
            WATER,
            "pipe",
            [("ew", f"out:{WATER}:0")],
            [("o", _pin(oven, WATER))],
            30,
        ),
        _net("g", GAS, "pipe", [("eg", f"out:{GAS}:0")], [("z", f"in:{GAS}:0")], 6),
    ]
    netlist = _netlist(
        dataset, WULING, [oven, unit, water, gas, parked_core(dataset, "core")], nets
    )
    _, layout = _run(dataset, netlist, seed=3)
    assert _errors(dataset, layout) == []
    x0, y0, x1, y1 = layout.area_rect
    assert len(layout.entries) == 2
    piped = {cell for s in layout.pipes() for cell in s.cells}
    piped |= {(u.x, u.y) for u in layout.units if "pipe" in u.unit_id}
    for entry in layout.entries:
        assert x0 <= entry.x < x1 and y0 <= entry.y < y1
        assert entry.x in (x0, x1 - 1) or entry.y in (y0, y1 - 1)
        assert entry.start in piped
    oven_placed = next(m for m in layout.machines if m.machine_id == "xiranite_oven_1")
    unit_placed = next(m for m in layout.machines if m.machine_id == "vaporizer_1")
    assert inside(
        (oven_placed.x, oven_placed.y, oven_placed.x + 5, oven_placed.y + 5),
        (
            unit_placed.x - ZONE_REACH,
            unit_placed.y - ZONE_REACH,
            unit_placed.x + 3 + ZONE_REACH,
            unit_placed.y + 3 + ZONE_REACH,
        ),
    )
    evaluation = evaluate(dataset, layout)
    assert evaluation.converged
    assert evaluation.machines[oven_placed.id].inputs[WATER] == 30


def test_a_laid_bus_seats_its_bricks_and_stays_one_cluster(dataset: Dataset) -> None:
    port = bus_part(dataset, "port", BUS_PORT)
    section = bus_part(dataset, "sec", BUS_SECTION)
    unloader = brick_cell(dataset, "u", "unloader", ORE, Fraction(30), "free")
    loader = brick_cell(dataset, "l", "loader", NUGGET, Fraction(10), "free")
    furnace = recipe_cell(dataset, "f", dataset.recipes["furnance_copper_nugget_1"])
    nets = [
        _net("ore", ORE, "belt", [("u", f"out:{ORE}:0")], [("f", _pin(furnace, ORE))]),
        _net(
            "nug",
            NUGGET,
            "belt",
            [("f", _pin(furnace, NUGGET))],
            [("l", f"in:{NUGGET}:0")],
            10,
        ),
    ]
    cells = [port, section, unloader, loader, furnace, parked_core(dataset, "core")]
    placement, layout = _run(dataset, _netlist(dataset, WULING, cells, nets), seed=5)
    rules = {f.rule for f in _errors(dataset, layout)}
    assert "endfield.bus" not in rules and "kl.legal" not in rules, rules
    assert _errors(dataset, layout) == []
    parts = {b.id: b for b in placement.blocks if b.id in ("port", "sec")}
    assert len(parts) == 2
    assert evaluate(dataset, layout).converged
    assert layout.belts()


def test_valley_bricks_take_slots_and_route_to_each_other(dataset: Dataset) -> None:
    unloader = brick_cell(dataset, "u", "unloader", ORE, Fraction(30))
    loader = brick_cell(dataset, "l", "loader", ORE, Fraction(30))
    nets = [_net("n", ORE, "belt", [("u", f"out:{ORE}:0")], [("l", f"in:{ORE}:0")])]
    netlist = _netlist(
        dataset, VALLEY, [unloader, loader, parked_core(dataset, "core")], nets
    )
    placement, layout = _run(dataset, netlist, seed=0)
    assert _errors(dataset, layout) == []
    assert io_budget(dataset, VALLEY) == 10
    slots = {(x, y) for x, y, _ in ()}
    for brick_id in ("u", "l"):
        block = placement.block(brick_id)
        slots.add((block.x, block.y))
    assert len(slots) == 2
    assert layout.belts()


def test_core_ports_carry_supply_and_delivery_when_asked(dataset: Dataset) -> None:
    core = core_cell(dataset, "core", [(ORE, Fraction(30))], [(NUGGET, Fraction(10))])
    furnace = recipe_cell(dataset, "f", dataset.recipes["furnance_copper_nugget_1"])
    nets = [
        _net(
            "ore", ORE, "belt", [("core", f"out:{ORE}:0")], [("f", _pin(furnace, ORE))]
        ),
        _net(
            "nug",
            NUGGET,
            "belt",
            [("f", _pin(furnace, NUGGET))],
            [("core", f"in:{NUGGET}:0")],
            10,
        ),
    ]
    netlist = _netlist(dataset, WULING, [core, furnace], nets)
    _, layout = _run(dataset, netlist, seed=4)
    assert _errors(dataset, layout) == []
    core_placed = next(m for m in layout.machines if m.machine_id == "sp_hub_1")
    assert core_placed.config.get("out0") == ORE
    assert evaluate(dataset, layout).converged


def test_cancellation_and_settings_that_cannot_run(dataset: Dataset) -> None:
    netlist = _furnace_pair(dataset)
    with pytest.raises(CancelledError):
        layout_stage(dataset, netlist, {**FAST}, None, lambda: True)
    with pytest.raises(StageError):
        params_of("layout", {"spread_gap": -1})
    with pytest.raises(StageError):
        params_of(
            "layout", {"solver": "regional", "solver_options": '{"attempts": -4}'}
        )


def test_area_rules_flag_production_in_the_ring_and_belts_outside(
    dataset: Dataset,
) -> None:
    layout = Layout(
        dataset_version=dataset.version.id,
        basement=WULING,
        width=50,
        height=50,
        area=(10, 10, 40, 40),
        machines=[
            Placed(id="hub", machine_id="sp_hub_1", x=20, y=20),
            Placed(id="stray", machine_id="furnance_1", x=2, y=2),
            Placed(id="pylon", machine_id="power_diffuser_1", x=5, y=30),
        ],
        segments=[Segment(id="b", kind="belt", cells=[(5, 12), (6, 12)])],
        entries=[
            Entry(id="bad", item_id=WATER, rate=Fraction(30), x=15, y=15, edge="W")
        ],
    )
    found = check_layout(dataset, layout)
    rules = {f.rule for f in found}
    assert "endfield.area" in rules and "endfield.belt_ring" in rules
    assert any(f.rule == "kl.legal" and f.subject == "cell:bad" for f in found)
    subjects = {f.subject for f in found if f.rule == "endfield.area"}
    assert subjects == {"cell:stray"}


def test_bus_rules_on_hand_built_layouts(dataset: Dataset) -> None:
    def layout_with(machines: list[Placed]) -> Layout:
        return Layout(
            dataset_version=dataset.version.id,
            basement=WULING,
            width=40,
            height=40,
            area=(0, 0, 40, 40),
            machines=machines,
        )

    port = Placed(id="port", machine_id=BUS_PORT, x=10, y=10)
    touching = Placed(id="sec", machine_id=BUS_SECTION, x=14, y=10)
    apart = Placed(id="sec", machine_id=BUS_SECTION, x=16, y=10)
    facing = Placed(id="u", machine_id="unloader_1", x=10, y=14, config={"item": ORE})
    turned = Placed(
        id="u", machine_id="unloader_1", x=10, y=14, rotation=180, config={"item": ORE}
    )
    good = _errors(dataset, layout_with([port, touching, facing]))
    assert good == []
    bad = _errors(dataset, layout_with([port, apart, turned]))
    assert {f.subject for f in bad if f.rule == "endfield.bus"} == {
        "cell:sec",
        "cell:u",
    }
    alone = {f.rule for f in _errors(dataset, layout_with([touching]))}
    assert "endfield.bus" in alone


def test_single_cell_helper_and_pin_defaults(dataset: Dataset) -> None:
    cell = single_cell(dataset, "d", "dump", "liquid_cleaner_1", [])
    assert cell.width == 3 and cell.height == 3 and len(cell.machines) == 1
    assert cell.machines[0].id == "d:m0" and cell.constraint == "free"
    assert cell.group is None
    entry = entry_cell("e", WATER, Fraction(120))
    assert entry.machines == [] and entry.constraint == "edge"
    assert entry.pins[0].edge == "E" and entry.pins[0].kind == "pipe"


def test_a_long_belt_is_cut_by_pass_through_splitters(
    dataset: Dataset, monkeypatch: pytest.MonkeyPatch
) -> None:
    limit = 3
    monkeypatch.setitem(carriers.RUN_LIMIT, "belt", limit)
    unloader = brick_cell(dataset, "u", "unloader", ORE, Fraction(30))
    loader = brick_cell(dataset, "l", "loader", ORE, Fraction(30))
    nets = [_net("n", ORE, "belt", [("u", f"out:{ORE}:0")], [("l", f"in:{ORE}:0")])]
    netlist = _netlist(
        dataset, VALLEY, [unloader, loader, parked_core(dataset, "core")], nets
    )
    _, layout = _run(dataset, netlist, seed=0)
    assert _errors(dataset, layout) == []
    assert sum(len(s.cells) for s in layout.segments) + len(layout.units) > limit
    assert all(len(s.cells) <= limit for s in layout.segments)
    assert [u.unit_id for u in layout.units].count("log_splitter") >= 1
    evaluation = evaluate(dataset, layout)
    assert evaluation.converged
    assert evaluation.machines["l:m0"].inputs == {ORE: 30}
