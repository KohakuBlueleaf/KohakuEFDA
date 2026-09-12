"""A footprint over one lane takes up that lane and the lanes hanging from it."""

from fractions import Fraction

from kohakulayout.engine import Budget, Context
from kohakulayout.ir import Cell, Net, Netlist, Pin, PinRef, Segment, Wire
from kohakulayout.templates.physics.gates import LIBRARY, GatesPhysics, problem


def _world():
    cells = {
        "a": Cell(
            id="a",
            footprint="IN",
            pins=(Pin(id="y", direction="out", carrier="wire", ports=("y",)),),
        ),
        "y": Cell(
            id="y",
            footprint="OUT",
            pins=(Pin(id="a", direction="in", carrier="wire", ports=("a",)),),
        ),
    }
    net = Net(
        id="m",
        carrier="wire",
        rate=Fraction(1),
        sources=(PinRef(cell="a", pin="y"),),
        sinks=(PinRef(cell="y", pin="a"),),
    )
    netlist = Netlist(pack="gates", library=dict(LIBRARY), cells=cells, nets={"m": net})
    ctx = Context(
        problem(netlist, width=16, height=8),
        physics=GatesPhysics(),
        seed=1,
        budget=Budget(units=50),
    )
    return ctx.world


def _segment(layer: str, cells: list[tuple[int, int]]) -> Segment:
    return Segment(carrier="wire", layer=layer, cells=tuple(cells))


def test_the_lane_a_taken_lane_joined_stays() -> None:
    world = _world()
    layer = world.carrier_layer("wire")
    parent = _segment(layer, [(x, 3) for x in range(1, 12)])
    child = _segment(layer, [(6, 0), (6, 1), (6, 2), (6, 3)])
    branch = _segment(layer, [(8, 3), (8, 4), (8, 5), (8, 6)])
    with world.transaction():
        assert world.place("a", 0, 3, 0) is None
        assert world.place("y", 12, 3, 0) is None
        world.set_wire(Wire(net="m", segments=(parent, child, branch)))
        assert world.trim("m", [(6, 1)])
        assert [list(s.cells) for s in world.wires["m"].segments] == [
            list(parent.cells),
            list(branch.cells),
        ]
        assert world.kernel.holders_at(layer, (6, 1)) == ()
        assert world.kernel.holders_at(layer, (6, 3)) == ("wire:m",)


def test_the_lanes_hanging_from_a_taken_lane_go_with_it() -> None:
    world = _world()
    layer = world.carrier_layer("wire")
    parent = _segment(layer, [(x, 3) for x in range(1, 12)])
    child = _segment(layer, [(6, 0), (6, 1), (6, 2), (6, 3)])
    branch = _segment(layer, [(8, 3), (8, 4), (8, 5), (8, 6)])
    with world.transaction():
        assert world.place("a", 0, 3, 0) is None
        assert world.place("y", 12, 3, 0) is None
        world.set_wire(Wire(net="m", segments=(parent, child, branch)))
        assert not world.trim("m", [(4, 3)])
        assert len(world.wires["m"].segments) == 3
