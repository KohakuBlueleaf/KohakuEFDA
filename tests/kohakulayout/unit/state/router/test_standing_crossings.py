"""A seed's crossing survives only while the kept segments still make it."""

from fractions import Fraction

from kohakulayout.engine import Budget, Context
from kohakulayout.ir import Cell, Net, Netlist, Pin, PinRef, Segment, Wire
from kohakulayout.state.router.lanes import standing_crossings
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
    nets = {
        name: Net(
            id=name,
            carrier="wire",
            rate=Fraction(1),
            sources=(PinRef(cell="a", pin="y"),),
            sinks=(PinRef(cell="y", pin="a"),),
        )
        for name in ("m", "n")
    }
    netlist = Netlist(pack="gates", library=dict(LIBRARY), cells=cells, nets=nets)
    ctx = Context(
        problem(netlist, width=16, height=8),
        physics=GatesPhysics(),
        seed=1,
        budget=Budget(units=50),
    )
    return ctx.world


def _segment(layer: str, cells: list[tuple[int, int]]) -> Segment:
    return Segment(carrier="wire", layer=layer, cells=tuple(cells))


def test_a_crossing_stays_only_while_its_partner_holds_the_cell() -> None:
    world = _world()
    layer = world.carrier_layer("wire")
    net = world.netlist.nets["m"]
    across = _segment(layer, [(6, 3), (7, 3), (8, 3), (9, 3), (10, 3)])
    down = _segment(layer, [(8, 0), (8, 1), (8, 2), (8, 3), (8, 4), (8, 5)])
    crossing = [((8, 3), "n", False)]
    with world.transaction():
        world.set_wire(Wire(net="n", segments=(across,)))
        assert standing_crossings(world, net, layer, crossing, [down]) == crossing
        assert standing_crossings(world, net, layer, crossing, []) == []
        world.unroute("n")
        assert standing_crossings(world, net, layer, crossing, [down]) == []


def test_an_own_crossing_needs_both_of_its_lanes_kept() -> None:
    world = _world()
    layer = world.carrier_layer("wire")
    net = world.netlist.nets["m"]
    across = _segment(layer, [(6, 3), (7, 3), (8, 3), (9, 3), (10, 3)])
    down = _segment(layer, [(8, 0), (8, 1), (8, 2), (8, 3), (8, 4), (8, 5)])
    crossing = [((8, 3), "m", False)]
    assert standing_crossings(world, net, layer, crossing, [across, down]) == crossing
    assert standing_crossings(world, net, layer, crossing, [down]) == []
