"""The layout engine on small hand-built netlists: wired machines end close and routed,
outside inputs on the border, bricks on a laid bus or on fixed slots, zones holding their
machines, the parked core inside the area, cancellation, and the rules on hand-built
layouts."""

from fractions import Fraction
from itertools import pairwise
from pathlib import Path

import numpy as np
import pytest

from kohakuefda.flow.evaluate import evaluate
from kohakuefda.layout.board import board_of
from kohakuefda.layout.coverage import cover, covered, inside, zone_rect
from kohakuefda.layout.depot_via import BUS_PORT, BUS_SECTION, io_budget
from kohakuefda.layout.engine import Engine, LayoutError
from kohakuefda.layout.stages import params_of
from kohakuefda.model.basement import Region
from kohakuefda.model.cells import CellInstance, Netlist, NetSpec, PinRef
from kohakuefda.model.control import CancelledError
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.layout import Entry, Layout, Placed, Segment
from kohakuefda.model.scenario import BasementRef, Scenario
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
from kohakuefda.route.router import PinKey
from kohakuefda.solvers.baseline.shrink import Shrink
from kohakuefda.verify.rules.geometry import check_layout

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
SEWAGE = "item_liquid_sewage"
GAS = "item_gas_inert"
FAST = {"workers": 1, "frame_every": 1000}


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


def _engine(dataset: Dataset, netlist: Netlist, **params) -> Engine:
    board = board_of(dataset, netlist.scenario)
    return Engine(dataset, netlist, board, params_of("layout", {**FAST, **params}))


def _errors(dataset: Dataset, layout: Layout) -> list:
    return [f for f in check_layout(dataset, layout) if f.severity == "error"]


def _pin(cell: CellInstance, item_id: str) -> str:
    return next(p for p in cell.pins if p.item_id == item_id).id


def _furnace_pair(dataset: Dataset) -> Netlist:
    """A Refining Unit feeding a Shredding Unit, the core parked beside them."""
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
    engine = _engine(dataset, _furnace_pair(dataset), seed=2)
    result = engine.run()
    assert result.fits and result.findings == []
    assert _errors(dataset, result.layout) == []
    furnace, grinder = engine.site.blocks["f"], engine.site.blocks["g"]
    assert abs(furnace.x - grinder.x) + abs(furnace.y - grinder.y) <= 10
    assert result.layout.segments and result.terms["length"] <= 12
    assert result.pylons and result.terms["pylons"] == 1
    assert result.terms["area"] <= 12 * 12


def test_the_parked_core_stays_inside_the_area_and_counts(dataset: Dataset) -> None:
    engine = _engine(dataset, _furnace_pair(dataset), seed=1)
    result = engine.run()
    assert result.fits and result.findings == []
    core = next(m for m in result.layout.machines if m.machine_id == "sp_hub_1")
    rect = (core.x, core.y, core.x + 9, core.y + 9)
    assert inside(rect, result.layout.area_rect)
    for other in result.layout.machines:
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
        for m in result.layout.machines
        if m.machine_id != "power_diffuser_1"
    )
    assert 9 * 9 < footprint <= result.terms["area"]


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
    result = _engine(dataset, netlist, seed=3).run()
    layout = result.layout
    assert result.findings == [] and _errors(dataset, layout) == []
    x0, y0, x1, y1 = layout.area_rect
    assert len(layout.entries) == 2
    piped = {cell for s in layout.pipes() for cell in s.cells}
    piped |= {(u.x, u.y) for u in layout.units if "pipe" in u.unit_id}
    for entry in layout.entries:
        assert entry.edge in ("N", "W")
        assert x0 <= entry.x < x1 and y0 <= entry.y < y1
        assert entry.x == x0 or entry.y == y0
        assert entry.start in piped
    oven_placed = next(m for m in layout.machines if m.machine_id == "xiranite_oven_1")
    unit_placed = next(m for m in layout.machines if m.machine_id == "vaporizer_1")
    assert inside(
        (oven_placed.x, oven_placed.y, oven_placed.x + 5, oven_placed.y + 5),
        zone_rect((unit_placed.x, unit_placed.y), 3),
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
    engine = _engine(dataset, _netlist(dataset, WULING, cells, nets), seed=5)
    result = engine.run()
    assert result.findings == [] and _errors(dataset, result.layout) == []
    groups = {name: sorted(b.id for b in m) for name, m in engine.site.groups.items()}
    assert groups == {"bus": ["l", "port", "sec", "u"]}
    assert engine.site.faults() == 0
    parts = {engine.site.blocks["port"].rect(), engine.site.blocks["sec"].rect()}
    assert len(parts) == 2
    for brick_id in ("u", "l"):
        brick = engine.site.blocks[brick_id]
        key = next(iter(brick.pins))
        assert brick.rotation in (0, 90, 180, 270)
        assert brick.pin_outside(key) not in set(engine.site.blocks["port"].cells())
    assert evaluate(dataset, result.layout).converged
    assert result.layout.belts()


def test_valley_bricks_take_slots_and_route_to_each_other(dataset: Dataset) -> None:
    unloader = brick_cell(dataset, "u", "unloader", ORE, Fraction(30))
    loader = brick_cell(dataset, "l", "loader", ORE, Fraction(30))
    nets = [_net("n", ORE, "belt", [("u", f"out:{ORE}:0")], [("l", f"in:{ORE}:0")])]
    netlist = _netlist(
        dataset, VALLEY, [unloader, loader, parked_core(dataset, "core")], nets
    )
    engine = _engine(dataset, netlist, seed=0)
    result = engine.run()
    assert result.findings == [] and _errors(dataset, result.layout) == []
    slots = {(s.x, s.y) for s in engine.board.slots}
    assert len(slots) == io_budget(dataset, VALLEY) == 10
    along = sorted(x for x, _ in slots)
    assert along == list(
        range(along[0], along[0] + 3 * len(along), 3)
    ), "gaps on the bus"
    for brick in engine.kinds("slot"):
        assert (brick.x, brick.y) in slots, brick.id
    assert result.layout.belts()


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
    result = _engine(dataset, netlist, seed=4).run()
    assert result.findings == [] and _errors(dataset, result.layout) == []
    core_placed = next(m for m in result.layout.machines if m.machine_id == "sp_hub_1")
    assert core_placed.config.get("out0") == ORE
    assert evaluate(dataset, result.layout).converged


def test_greedy_cover_on_a_known_pattern(dataset: Dataset) -> None:
    pylon = dataset.pylons["power_diffuser_1"]
    blocked = np.zeros((30, 30), dtype=bool)
    targets = [(4, 4, 7, 7), (9, 4, 12, 7), (4, 9, 7, 12), (9, 9, 12, 12)]
    for x0, y0, x1, y1 in targets:
        blocked[y0:y1, x0:x1] = True
    result = cover(pylon, targets, blocked, (8, 8))
    assert len(result.pylons) == 1 and not result.uncovered
    assert all(covered(pylon, result.pylons, t) for t in targets)
    far = targets + [(24, 24, 27, 27)]
    blocked[24:27, 24:27] = True
    result = cover(pylon, far, blocked, (8, 8))
    assert len(result.pylons) == 2 and not result.uncovered
    walled = np.ones((30, 30), dtype=bool)
    assert cover(pylon, targets, walled, (8, 8)).uncovered == targets


def test_the_line_is_solid_and_cannot_be_pulled_closer_to_the_corner(
    dataset: Dataset,
) -> None:
    engine = _engine(dataset, _furnace_pair(dataset), seed=7)
    result = engine.run()
    assert result.fits and result.findings == []
    used = engine.site.occupied()
    x0, y0, x1, y1 = engine.site.bbox()
    empty_rows = [y for y in range(y0, y1) if not any(c[1] == y for c in used)]
    empty_cols = [x for x in range(x0, x1) if not any(c[0] == x for c in used)]
    assert empty_rows == [] and empty_cols == []
    ctx = engine.runner.context
    before = ctx.current.id
    Shrink(ctx, tuple(i for i, _ in ctx.view.anchors), 200).run()
    assert ctx.current.id == before


def test_the_squeeze_measures_the_layout_that_gets_reported(dataset: Dataset) -> None:
    """What the squeeze calls smaller has to be what the report calls smaller.

    They parted once: the squeeze read the grid's own extent, which counts pipe that ran out
    through the ring and no pylon at all, so it could take a move that grew the built layout.
    """
    engine = _engine(dataset, _furnace_pair(dataset), seed=7)
    engine.run()
    area, wires = engine.runner.context.objective.key(
        engine.runner.context.current.assessment
    )
    reported = engine.measure(engine.site)
    assert (area, wires) == (reported[2], reported[3])


def test_every_greedy_improvement_is_whole_and_smaller(dataset: Dataset) -> None:
    engine = _engine(dataset, _furnace_pair(dataset), seed=7, shrink_rounds=0)
    engine.run()
    ctx = engine.runner.context
    sizes = [ctx.objective.key(ctx.current.assessment)]

    def observe(event) -> None:
        if event.kind == "accepted":
            assert not ctx.view.missing and not ctx.view.unrouted
            sizes.append(ctx.objective.key(ctx.current.assessment))

    ctx.observe = observe
    Shrink(ctx, tuple(i for i, _ in ctx.view.anchors), 200).run()
    assert len(sizes) > 1
    assert all(after < before for before, after in pairwise(sizes))


def test_cancellation_and_a_budget_that_cannot_run(dataset: Dataset) -> None:
    netlist = _furnace_pair(dataset)
    with pytest.raises(CancelledError):
        _engine(dataset, netlist, workers=1).run(None, lambda: True)
    with pytest.raises(LayoutError):
        _engine(dataset, netlist, spread_gap=-1)
    with pytest.raises(LayoutError):
        _engine(dataset, netlist, spread_gap=4, spread_widest=2)


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
    rules = {f.rule for f in check_layout(dataset, layout)}
    assert "geom.outside_area" in rules and "geom.belt_in_ring" in rules
    assert "geom.entry_off_border" in rules
    assert "geom.core_missing" not in rules
    subjects = {
        f.subject
        for f in check_layout(dataset, layout)
        if f.rule == "geom.outside_area"
    }
    assert subjects == {"stray"}


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
    good = {f.rule for f in _errors(dataset, layout_with([port, touching, facing]))}
    assert "geom.bus_connected" not in good and "geom.depot_bus" not in good
    bad = {f.rule for f in _errors(dataset, layout_with([port, apart, turned]))}
    assert "geom.bus_connected" in bad and "geom.depot_bus" in bad
    alone = {f.rule for f in _errors(dataset, layout_with([touching]))}
    assert "geom.bus_connected" in alone


def test_single_cell_helper_and_pin_defaults(dataset: Dataset) -> None:
    cell = single_cell(dataset, "d", "dump", "liquid_cleaner_1", [])
    assert cell.width == 3 and cell.height == 3 and len(cell.machines) == 1
    assert cell.machines[0].id == "d:m0" and cell.constraint == "free"
    assert cell.group is None
    entry = entry_cell("e", WATER, Fraction(120))
    assert entry.machines == [] and entry.constraint == "edge"
    assert entry.pins[0].edge == "E" and entry.pins[0].kind == "pipe"
