"""Layout geometry rules and steady-state evaluation on hand-built lines."""

from fractions import Fraction
from pathlib import Path

import pytest

from kohakuefda.model.basement import Region
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.geometry import Edge
from kohakuefda.model.layout import Layout, Link, Placed, Segment, Unit
from kohakuefda.model.scenario import BasementRef
from kohakuefda.render.grid_text import render_text
from kohakuefda.synth.reverse import Connections
from kohakuefda.verify.evaluate import evaluate
from kohakuefda.verify.layout import check_layout

DATASET = (
    Path(__file__).resolve().parents[1] / "data" / "1.5.3@9764758-3" / "dataset.json"
)
BASEMENT = BasementRef(
    region=Region.WULING, basement_id="sky_king_flats", level=1, depot_level=1
)
ORE = "item_originium_ore"
SEWAGE = "item_liquid_sewage"
WATER = "item_liquid_water"


@pytest.fixture(scope="module")
def dataset() -> Dataset:
    return Dataset.load(DATASET)


def item_named(dataset: Dataset, name: str) -> str:
    return next(i.id for i in dataset.items.values() if i.names.en == name)


def origocrust_recipe(dataset: Dataset) -> str:
    return next(
        r.id
        for r in dataset.recipes_for(item_named(dataset, "Origocrust"))
        if r.machine_id == "furnance_1" and r.mode == "normal"
    )


def errors(dataset: Dataset, layout: Layout) -> list:
    return [f for f in check_layout(dataset, layout) if f.severity == "error"]


def straight_line(dataset: Dataset) -> Layout:
    """Bus → Depot Unloader (ore) → belt → Refining Unit → belt → Depot Loader → bus, facing south."""
    return Layout(
        dataset_version=dataset.version.id,
        basement=BASEMENT,
        width=5,
        height=18,
        machines=[
            Placed(id="bus_top", machine_id="log_hongs_bus_source", x=0, y=0),
            Placed(
                id="unloader", machine_id="unloader_1", x=0, y=4, config={"item": ORE}
            ),
            Placed(
                id="refine",
                machine_id="furnance_1",
                x=0,
                y=8,
                mode="normal",
                recipe_id=origocrust_recipe(dataset),
            ),
            Placed(id="loader", machine_id="loader_1", x=0, y=13),
            Placed(id="bus_bottom", machine_id="log_hongs_bus_source", x=0, y=14),
            Placed(id="pylon", machine_id="power_diffuser_1", x=3, y=8),
        ],
        segments=[
            Segment(id="belt_in", kind="belt", cells=[(1, 5), (1, 6), (1, 7)]),
            Segment(id="belt_out", kind="belt", cells=[(1, 11), (1, 12)]),
        ],
    )


def test_ports_connect_end_to_end(dataset: Dataset) -> None:
    layout = straight_line(dataset)
    conn = Connections(dataset, layout)
    source, target = conn.ends["belt_in"]
    assert source is not None and source.owner == "unloader"
    assert target is not None and target.owner == "refine"
    source, target = conn.ends["belt_out"]
    assert source is not None and source.owner == "refine"
    assert target is not None and target.owner == "loader"


def test_clean_line_passes_drc_and_runs_at_full_rate(dataset: Dataset) -> None:
    layout = straight_line(dataset)
    assert errors(dataset, layout) == []
    result = evaluate(dataset, layout)
    assert result.converged
    assert result.machines["refine"].utilisation == Fraction(1)
    assert result.segments["belt_in"].total == Fraction(30)
    assert result.segments["belt_out"].items == {
        item_named(dataset, "Origocrust"): Fraction(30)
    }
    assert "bus_top" not in result.machines
    text = render_text(dataset, layout)
    assert "v" in text and "R" in text


def test_missing_outlet_stalls_the_machine(dataset: Dataset) -> None:
    layout = straight_line(dataset)
    layout.segments = layout.segments[:1]
    result = evaluate(dataset, layout)
    assert result.machines["refine"].utilisation == 0
    assert result.machines["refine"].stalled_by.startswith("no outlet")


def test_overlap_gap_and_merge_are_reported(dataset: Dataset) -> None:
    layout = straight_line(dataset)
    layout.machines.append(Placed(id="clash", machine_id="grinder_1", x=1, y=9))
    layout.segments.append(Segment(id="gap", kind="belt", cells=[(4, 5), (4, 7)]))
    layout.segments.append(
        Segment(id="second_in", kind="belt", cells=[(4, 5), (4, 6), (1, 7)])
    )
    rules = {f.rule for f in check_layout(dataset, layout)}
    assert {"kl.occupancy", "kl.geometry", "endfield.wiring"} <= rules


def test_pipe_over_machine_and_bounds(dataset: Dataset) -> None:
    layout = straight_line(dataset)
    layout.segments.append(
        Segment(id="pipe0", kind="pipe", cells=[(0, 9), (1, 9), (2, 9)])
    )
    layout.machines.append(Placed(id="edge", machine_id="grinder_1", x=4, y=0))
    found = check_layout(dataset, layout)
    rules = {f.rule for f in found}
    assert "kl.occupancy" in rules and "kl.geometry" in rules
    assert any(f.rule == "kl.occupancy" and f.subject == "cell:refine" for f in found)


def test_depot_bus_must_touch_loaders(dataset: Dataset) -> None:
    layout = straight_line(dataset)
    layout.machines = [m for m in layout.machines if m.id != "bus_bottom"]
    found = [f for f in check_layout(dataset, layout) if f.rule == "endfield.bus"]
    assert [(f.severity, f.subject) for f in found] == [("error", "cell:loader")]
    layout.machines = [m for m in layout.machines if m.id != "bus_top"]
    found = [f for f in check_layout(dataset, layout) if f.rule == "endfield.bus"]
    assert sorted((f.severity, f.subject) for f in found) == [
        ("error", "cell:loader"),
        ("error", "cell:unloader"),
    ]


def test_splitter_shares_between_live_outputs(dataset: Dataset) -> None:
    layout = Layout(
        dataset_version=dataset.version.id,
        basement=BASEMENT,
        width=9,
        height=19,
        machines=[
            Placed(id="bus_top", machine_id="log_hongs_bus_source", x=3, y=0),
            Placed(
                id="unloader", machine_id="unloader_1", x=3, y=4, config={"item": ORE}
            ),
            Placed(
                id="left",
                machine_id="furnance_1",
                x=0,
                y=9,
                recipe_id=origocrust_recipe(dataset),
            ),
            Placed(
                id="right",
                machine_id="furnance_1",
                x=6,
                y=9,
                recipe_id=origocrust_recipe(dataset),
            ),
            Placed(id="sink_l", machine_id="loader_1", x=0, y=14),
            Placed(id="sink_r", machine_id="loader_1", x=6, y=14),
            Placed(id="bus_bottom", machine_id="log_hongs_bus_source", x=0, y=15),
            Placed(id="bus_bottom_r", machine_id="log_hongs_bus_source", x=5, y=15),
            Placed(id="pylon", machine_id="power_diffuser_1", x=3, y=10),
        ],
        units=[Unit(id="split", unit_id="log_splitter", x=4, y=7)],
        segments=[
            Segment(id="feed", kind="belt", cells=[(4, 5), (4, 6)]),
            Segment(id="to_left", kind="belt", cells=[(3, 7), (2, 7), (1, 7), (1, 8)]),
            Segment(id="to_right", kind="belt", cells=[(5, 7), (6, 7), (7, 7), (7, 8)]),
            Segment(id="out_l", kind="belt", cells=[(1, 12), (1, 13)]),
            Segment(id="out_r", kind="belt", cells=[(7, 12), (7, 13)]),
        ],
    )
    assert errors(dataset, layout) == []
    result = evaluate(dataset, layout)
    assert result.segments["to_left"].total == Fraction(15)
    assert result.segments["to_right"].total == Fraction(15)
    assert result.machines["left"].utilisation == Fraction(1, 2)


def conduit_line(dataset: Dataset, item: str) -> Layout:
    """Fluid Pump → pipe → Conduit Inlet ⇢ Conduit Outlet → pipe → Water Treatment Unit."""
    return Layout(
        dataset_version=dataset.version.id,
        basement=BASEMENT,
        width=9,
        height=10,
        machines=[
            Placed(id="pump", machine_id="pump_1", x=0, y=1, config={"item": item}),
            Placed(
                id="inlet",
                machine_id="udpipe_loader_1",
                x=5,
                y=1,
                config={"item": item},
            ),
            Placed(id="outlet", machine_id="udpipe_unloader_1", x=0, y=6),
            Placed(id="dump", machine_id="liquid_cleaner_1", x=5, y=6),
            Placed(id="pylon", machine_id="power_diffuser_1", x=3, y=4),
        ],
        segments=[
            Segment(id="pipe_a", kind="pipe", cells=[(3, 2), (4, 2)]),
            Segment(id="pipe_b", kind="pipe", cells=[(3, 7), (4, 7)]),
        ],
        links=[Link(inlet="inlet", outlet="outlet")],
    )


def test_conduit_carries_flow_and_dump_caps_it(dataset: Dataset) -> None:
    layout = conduit_line(dataset, SEWAGE)
    assert errors(dataset, layout) == []
    result = evaluate(dataset, layout)
    assert result.converged
    assert result.segments["pipe_a"].total == Fraction(30)
    assert result.segments["pipe_b"].items == {SEWAGE: Fraction(30)}
    assert result.machines["dump"].utilisation == Fraction(1)


def test_dump_rejects_items_it_cannot_treat(dataset: Dataset) -> None:
    result = evaluate(dataset, conduit_line(dataset, WATER))
    assert result.segments["pipe_b"].total == 0
    assert result.segments["pipe_a"].total == 0
    assert result.machines["inlet"].stalled_by == "nothing received"


def test_two_touching_machines_transfer_nothing(dataset: Dataset) -> None:
    """A connection always costs a belt cell: an unloader's port against a loader's port
    feeds it nothing (game-knowledge LOG-11)."""
    layout = Layout(
        dataset_version=dataset.version.id,
        basement=BasementRef(
            region=Region.VALLEY4, basement_id="infra_station", level=1, depot_level=1
        ),
        width=6,
        height=4,
        machines=[
            Placed(
                id="unloader", machine_id="unloader_1", x=0, y=0, config={"item": ORE}
            ),
            Placed(id="loader", machine_id="loader_1", x=0, y=1),
        ],
    )
    assert Connections(dataset, layout).links == []
    assert evaluate(dataset, layout).machines["loader"].inputs == {}


def test_touching_units_connect_directly(dataset: Dataset) -> None:
    """Unloader → belt → splitter touching a bridge → belt → loader; without an area the
    Valley IV bus cannot be located, so the bus rule stays silent."""
    layout = Layout(
        dataset_version=dataset.version.id,
        basement=BasementRef(
            region=Region.VALLEY4, basement_id="infra_station", level=1, depot_level=1
        ),
        width=4,
        height=8,
        machines=[
            Placed(
                id="unloader", machine_id="unloader_1", x=0, y=0, config={"item": ORE}
            ),
            Placed(id="loader", machine_id="loader_1", x=0, y=6),
        ],
        units=[
            Unit(id="split", unit_id="log_splitter", x=1, y=2),
            Unit(id="bridge", unit_id="log_connector", x=1, y=3),
        ],
        segments=[
            Segment(id="feed", kind="belt", cells=[(1, 1)], heading=Edge.S),
            Segment(id="out", kind="belt", cells=[(1, 4), (1, 5)]),
        ],
    )
    assert errors(dataset, layout) == []
    links = Connections(dataset, layout).links
    assert [(a.owner, b.owner) for a, b in links] == [("split", "bridge")]
    result = evaluate(dataset, layout)
    assert result.machines["loader"].inputs == {ORE: Fraction(30)}
