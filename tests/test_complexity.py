"""Build complexity read from a layout: wire cells, bends, junctions, bridges, kinds, straightness."""

from fractions import Fraction

from kohakuefda.model.basement import Region
from kohakuefda.model.layout import Layout, Placed, Segment, Unit
from kohakuefda.model.scenario import BasementRef
from kohakuefda.verify.complexity import Complexity, complexity, complexity_text, runs


def _layout() -> Layout:
    basement = BasementRef(
        region=Region.VALLEY4, basement_id="the_hub", level=1, depot_level=1
    )
    return Layout(
        dataset_version="test",
        basement=basement,
        width=30,
        height=30,
        machines=[
            Placed(id="a", machine_id="grinder_1", x=2, y=2),
            Placed(id="b", machine_id="grinder_1", x=10, y=2),
            Placed(id="c", machine_id="furnance_1", x=18, y=2),
        ],
        units=[
            Unit(id="s", unit_id="log_splitter", x=6, y=6),
            Unit(id="k", unit_id="log_connector", x=8, y=6),
            Unit(id="p", unit_id="log_pipe_splitter", x=8, y=12),
            Unit(id="y", unit_id="power_diffuser_1", x=0, y=0),
        ],
        segments=[
            Segment(id="w1", kind="belt", cells=[(x, 6) for x in range(2, 14)]),
            Segment(
                id="w2",
                kind="belt",
                cells=[(14, 6), (15, 6), (15, 7), (15, 8), (16, 8)],
            ),
            Segment(id="w3", kind="pipe", cells=[(x, 12) for x in range(2, 10)]),
        ],
    )


def test_runs_split_a_segment_at_its_bends() -> None:
    layout = _layout()
    assert runs(layout.segments[0]) == [12]
    assert runs(layout.segments[1]) == [2, 3, 2]
    assert runs(Segment(id="one", kind="belt", cells=[(0, 0)])) == [1]


def test_complexity_counts_wire_bends_junctions_bridges_and_kinds() -> None:
    found = complexity(_layout())
    assert found == Complexity(
        belt_cells=17,
        pipe_cells=8,
        bends=2,
        splitters=1,
        convergers=0,
        belt_bridges=1,
        pipe_junctions=1,
        pipe_bridges=0,
        kinds=6,
        straight=Fraction(20, 25),
    )
    assert found.junctions == 2 and found.bridges == 1
    assert complexity_text(found).startswith("belts=17 pipes=8 bends=2 junctions=2")
    assert (
        complexity(
            Layout(dataset_version="t", basement=_layout().basement, width=4, height=4)
        ).straight
        == 0
    )
