"""A wire's run on a cell is the sides it continues to, and it goes with its wire."""

from fractions import Fraction

from kohakulayout.engine import Budget, Context
from kohakulayout.ir import Cell, Net, Netlist, Pin, PinRef, Segment, Wire
from kohakulayout.state.crossing import straight_through
from kohakulayout.templates.physics.gates import LIBRARY, GatesPhysics, problem
from kohakulayout.templates.physics.gates.library import JUMPER


def _cells() -> dict[str, Cell]:
    out = {
        "a": Cell(
            id="a",
            footprint="IN",
            pins=(Pin(id="y", direction="out", carrier="wire", ports=("y",)),),
        ),
        "b": Cell(
            id="b",
            footprint="IN",
            pins=(Pin(id="y", direction="out", carrier="wire", ports=("y",)),),
        ),
    }
    for name in ("y", "z"):
        out[name] = Cell(
            id=name,
            footprint="OUT",
            pins=(Pin(id="a", direction="in", carrier="wire", ports=("a",)),),
        )
    return out


def _net(id: str, source: str, sink: str) -> Net:
    return Net(
        id=id,
        carrier="wire",
        rate=Fraction(1),
        sources=(PinRef(cell=source, pin="y"),),
        sinks=(PinRef(cell=sink, pin="a"),),
    )


def _world():
    netlist = Netlist(
        pack="gates",
        library=dict(LIBRARY),
        cells=_cells(),
        nets={"n": _net("n", "a", "y"), "m": _net("m", "b", "z")},
    )
    ctx = Context(
        problem(netlist, width=24, height=7),
        physics=GatesPhysics(),
        seed=1,
        budget=Budget(units=50),
    )
    return ctx.world


def _columns(world, xs: tuple[int, ...]) -> Wire:
    layer = world.carrier_layer("wire")
    return Wire(
        net="m",
        segments=tuple(
            Segment(carrier="wire", layer=layer, cells=tuple((x, y) for y in range(7)))
            for x in xs
        ),
    )


def test_lanes_side_by_side_are_each_straight_through() -> None:
    world = _world()
    layer = world.carrier_layer("wire")
    with world.transaction():
        assert world.place("b", 7, 0, 0) is None
        assert world.place("z", 11, 6, 0) is None
        world.set_wire(_columns(world, (8, 9)))
        for x in (8, 9):
            assert world.kernel.run_at(layer, "wire:m", (x, 3)) == 5
            assert straight_through(world, layer, "m", (x, 3), (-1, 0))
            assert not straight_through(world, layer, "m", (x, 3), (0, 1))
        assert world.place("a", 0, 3, 0) is None
        assert world.place("y", 16, 3, 0) is None
        assert list(world.wires["n"].segments[0].cells) == [
            (x, 3) for x in range(1, 16)
        ]
        jumpers = sorted(
            (u.x, u.y) for u in world.units.values() if u.footprint == JUMPER.id
        )
        assert jumpers == [(8, 3), (9, 3)]


def test_a_run_reads_the_port_behind_an_attach_cell_and_goes_with_its_wire() -> None:
    world = _world()
    layer = world.carrier_layer("wire")
    with world.transaction():
        assert world.place("b", 7, 0, 0) is None
        assert world.place("z", 9, 6, 0) is None
        world.set_wire(_columns(world, (8,)))
        assert world.kernel.run_at(layer, "wire:m", (8, 0)) == 4 | 8
        assert world.kernel.run_at(layer, "wire:m", (8, 6)) == 1 | 2
        assert straight_through(world, layer, "m", (8, 6), (0, 1), bent=True)
        world.unroute("m")
        assert world.kernel.run_at(layer, "wire:m", (8, 3)) == 0
        assert not straight_through(world, layer, "m", (8, 3), (-1, 0))
