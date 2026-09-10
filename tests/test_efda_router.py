"""The project's router routes the nets one placement touches in the engine's lane order: pipes first, a pipe tree's trunk, joins and branches in that order, then the higher rate, then the wider span; the framework's default takes the widest first."""

from fractions import Fraction

from kohakuefda.layout.router import EndfieldRouter, lanes_at, tree_lane
from kohakuefda.physics.facts import lane_fact, pin_fact
from kohakulayout.ir import Cell, Net, Netlist, Pin, PinRef
from kohakulayout.state import DefaultRouter, World
from kohakulayout.templates.physics.gates import LIBRARY, GatesPhysics, problem


def _cell(cell_id: str, footprint: str, pins: tuple[tuple[str, str], ...]) -> Cell:
    return Cell(
        id=cell_id,
        footprint=footprint,
        pins=tuple(
            Pin(id=pin, direction=direction, carrier="wire", ports=(pin,))
            for pin, direction in pins
        ),
    )


def _problem(pair_rate: Fraction = Fraction(1)):
    netlist = Netlist(
        pack="gates",
        library=dict(LIBRARY),
        cells={
            "a": _cell("a", "IN", (("y", "out"),)),
            "b": _cell("b", "IN", (("y", "out"),)),
            "g": _cell("g", "AND", (("a", "in"), ("b", "in"), ("y", "out"))),
            "o0": _cell("o0", "OUT", (("a", "in"),)),
            "o1": _cell("o1", "OUT", (("a", "in"),)),
        },
        nets={
            "wide": Net(
                id="wide",
                carrier="wire",
                rate=Fraction(1),
                sources=(PinRef(cell="a", pin="y"),),
                sinks=(PinRef(cell="g", pin="a"), PinRef(cell="o1", pin="a")),
            ),
            "pair": Net(
                id="pair",
                carrier="wire",
                rate=pair_rate,
                sources=(PinRef(cell="b", pin="y"),),
                sinks=(PinRef(cell="g", pin="b"),),
            ),
            "out": Net(
                id="out",
                carrier="wire",
                rate=Fraction(1),
                sources=(PinRef(cell="g", pin="y"),),
                sinks=(PinRef(cell="o0", pin="a"),),
            ),
        },
    )
    return problem(netlist, width=20, height=10)


def _routed(router, pair_rate: Fraction = Fraction(1)) -> list[str]:
    world = World(_problem(pair_rate), GatesPhysics(), router=router)
    routed: list[str] = []
    inner = world.route

    def spy(net_id: str, grow: bool = False):
        routed.append(net_id)
        return inner(net_id, grow)

    world.route = spy
    with world.transaction() as tx:
        assert world.place("a", 0, 2) is None
        assert world.place("o1", 18, 2) is None
        assert world.place("b", 0, 6) is None
        assert world.place("o0", 18, 6) is None
        routed.clear()
        assert world.place("g", 8, 3) is None
        tx.commit()
    assert set(world.wires) == {"wide", "pair", "out"}
    return routed


def test_the_project_router_routes_the_wider_span_first_whatever_the_tree() -> None:
    assert _routed(EndfieldRouter()) == ["out", "wide", "pair"]


def test_the_project_router_routes_the_higher_rate_before_the_wider_span() -> None:
    assert _routed(EndfieldRouter(), Fraction(2)) == ["pair", "out", "wide"]


def test_the_default_router_routes_the_widest_first() -> None:
    assert _routed(DefaultRouter()) == ["wide", "out", "pair"]


class _Placed:
    """A world that only knows where pins attach and what the cells are."""

    def __init__(
        self, cells: dict[str, Cell], at: dict[tuple[str, str], tuple[int, int]]
    ):
        self.netlist = Netlist(pack="gates", library=dict(LIBRARY), cells=cells)
        self.at = at

    def attach_cell(self, cell_id: str, pin_id: str):
        return self.at.get((cell_id, pin_id))


def _pipe_tree() -> tuple[_Placed, Net]:
    cells = {
        "s1": Cell(
            id="s1",
            pins=(Pin(id="o", direction="out", carrier="pipe"),),
            attrs={"endfield": {"pins": [pin_fact("o", "water", Fraction(60))]}},
        ),
        "s2": Cell(
            id="s2",
            pins=(Pin(id="o", direction="out", carrier="pipe"),),
            attrs={"endfield": {"pins": [pin_fact("o", "water", Fraction(20))]}},
        ),
        "t1": Cell(
            id="t1",
            pins=(Pin(id="i", direction="in", carrier="pipe"),),
            attrs={"endfield": {"pins": [pin_fact("i", "water", Fraction(50))]}},
        ),
        "t2": Cell(
            id="t2",
            pins=(Pin(id="i", direction="in", carrier="pipe"),),
            attrs={"endfield": {"pins": [pin_fact("i", "water", Fraction(30))]}},
        ),
    }
    net = Net(
        id="w",
        carrier="pipe",
        rate=Fraction(80),
        sources=(PinRef(cell="s1", pin="o"), PinRef(cell="s2", pin="o")),
        sinks=(PinRef(cell="t1", pin="i"), PinRef(cell="t2", pin="i")),
    )
    return _Placed(cells, {}), net


def test_a_pipe_tree_ranks_its_trunk_then_a_join_then_a_branch() -> None:
    world, net = _pipe_tree()
    root, main = ("s1", "o"), ("t1", "i")
    assert tree_lane(world, net, "t1", False) == (0, [(root, main, Fraction(60))])
    assert tree_lane(world, net, "s2", True) == (1, [(("s2", "o"), main, Fraction(20))])
    assert tree_lane(world, net, "t2", True) == (3, [(root, ("t2", "i"), Fraction(30))])


def test_a_net_ranks_by_the_lanes_at_the_cell_or_all_when_only_disturbed() -> None:
    world, net = _pipe_tree()
    lanes = [
        lane_fact(("s1", "o"), ("t1", "i"), Fraction(50)),
        lane_fact(("s1", "o"), ("t2", "i"), Fraction(10)),
        lane_fact(("s2", "o"), ("t2", "i"), Fraction(20)),
    ]
    net = net.model_copy(update={"attrs": {"endfield": {"lanes": lanes}}})
    assert [lane[2] for lane in lanes_at(world, net, "t2")] == [
        Fraction(10),
        Fraction(20),
    ]
    assert len(lanes_at(world, net, "elsewhere")) == 3
    bare = net.model_copy(update={"attrs": {}})
    assert len(lanes_at(world, bare, "elsewhere")) == 4


def test_a_disturbed_pipe_tree_and_an_outside_fed_net_still_rank() -> None:
    world, net = _pipe_tree()
    root, main = ("s1", "o"), ("t1", "i")
    assert tree_lane(world, net, "elsewhere", True) == (0, [(root, main, Fraction(60))])
    fed = Net(id="f", carrier="wire", rate=Fraction(3), outside="W", sinks=net.sinks)
    assert lanes_at(world, fed, "t1") == []
