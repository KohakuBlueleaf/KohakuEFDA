"""A crossing unit stands only where the pack allows units."""

from fractions import Fraction

from kohakulayout.engine import Budget, Context
from kohakulayout.ir import (
    Carrier,
    Cell,
    Fabric,
    Footprint,
    Net,
    Netlist,
    Pin,
    PinRef,
    Problem,
    Region,
)
from kohakulayout.templates.physics.gates import LIBRARY, GatesPhysics
from kohakulayout.templates.physics.gates.boundaries import GatesBoundaries
from kohakulayout.templates.physics.gates.library import JUMPER

WIDTH, HEIGHT = 16, 7


class EdgeBoundaries(GatesBoundaries):
    def crossing_region(self, carrier: str, region: str) -> bool:
        return True

    def unit_region(self, unit: Footprint, region: str) -> bool:
        return region != "edge"


class OpenBoundaries(EdgeBoundaries):
    def unit_region(self, unit: Footprint, region: str) -> bool:
        return True


class EdgePhysics(GatesPhysics):
    id = "gates-edge"

    def __init__(self) -> None:
        super().__init__()
        self.boundaries = EdgeBoundaries()


class OpenPhysics(GatesPhysics):
    id = "gates-open"

    def __init__(self) -> None:
        super().__init__()
        self.boundaries = OpenBoundaries()


def _problem(physics: GatesPhysics) -> Problem:
    cells = {
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
        "y": Cell(
            id="y",
            footprint="OUT",
            pins=(Pin(id="a", direction="in", carrier="wire", ports=("a",)),),
        ),
        "z": Cell(
            id="z",
            footprint="OUT",
            pins=(Pin(id="a", direction="in", carrier="wire", ports=("a",)),),
        ),
    }
    nets = {
        "n": Net(
            id="n",
            carrier="wire",
            rate=Fraction(1),
            sources=(PinRef(cell="a", pin="y"),),
            sinks=(PinRef(cell="y", pin="a"),),
        ),
        "m": Net(
            id="m",
            carrier="wire",
            rate=Fraction(1),
            sources=(PinRef(cell="b", pin="y"),),
            sinks=(PinRef(cell="z", pin="a"),),
        ),
    }
    every = frozenset((x, y) for y in range(HEIGHT) for x in range(WIDTH))
    edge = frozenset(xy for xy in every if xy[0] < 4)
    fabric = Fabric(
        width=WIDTH,
        height=HEIGHT,
        layers=("ground", "overhead"),
        carriers={
            "wire": Carrier(id="wire", layer="ground"),
            "clk": Carrier(id="clk", layer="overhead"),
        },
        regions={"build": Region.of("build", every), "edge": Region.of("edge", edge)},
    )
    netlist = Netlist(pack=physics.id, library=dict(LIBRARY), cells=cells, nets=nets)
    return Problem(physics=physics.ref, fabric=fabric, netlist=netlist)


def _crossing_case(physics: GatesPhysics):
    """Net m runs down column 2 inside the edge; net n from (1, 3) must cross it."""
    ctx = Context(_problem(physics), physics=physics, seed=1, budget=Budget(units=50))
    world = ctx.world
    with world.transaction():
        assert world.place("b", 1, 0, 0) is None
        assert world.place("z", 3, 6, 0) is None
        assert list(world.wires["m"].segments[0].cells) == [(2, y) for y in range(7)]
        assert world.place("a", 0, 3, 0) is None
        assert world.place("y", 10, 3, 0) is None
        return sorted(
            (u.x, u.y) for u in world.units.values() if u.footprint == JUMPER.id
        )


def test_a_crossing_unit_keeps_out_of_a_region_closed_to_units() -> None:
    jumpers = _crossing_case(EdgePhysics())
    assert jumpers and all(x >= 4 for x, _ in jumpers)


def test_the_same_crossing_stands_in_place_where_units_are_allowed() -> None:
    assert _crossing_case(OpenPhysics()) == [(2, 3)]
