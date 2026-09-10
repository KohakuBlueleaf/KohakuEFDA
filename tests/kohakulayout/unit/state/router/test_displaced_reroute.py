"""A displaced net re-routes without displacing anyone: when its only way back would rip a third net, the route that displaced it is refused and nothing moves."""

from fractions import Fraction

from kohakulayout.ir import Cell, Net, Netlist, Pin, PinRef
from kohakulayout.physics import CrossingRule
from kohakulayout.state import DefaultRouter, World
from kohakulayout.state.router.protocol import Costs
from kohakulayout.templates.physics.gates import LIBRARY, GatesPhysics, problem
from kohakulayout.templates.physics.gates.carriers import GatesCarriers


class NoCrossings(GatesCarriers):
    def crossing(self, a: str, b: str) -> CrossingRule:
        return CrossingRule(mode="forbidden")


def _io(cell_id: str, footprint: str, pin: str, direction: str) -> Cell:
    return Cell(
        id=cell_id,
        footprint=footprint,
        pins=(Pin(id=pin, direction=direction, carrier="wire", ports=(pin,)),),
    )


def _net(net_id: str, source: str, sink: str) -> Net:
    return Net(
        id=net_id,
        carrier="wire",
        rate=Fraction(1),
        sources=(PinRef(cell=source, pin="y"),),
        sinks=(PinRef(cell=sink, pin="a"),),
    )


def _world() -> World:
    netlist = Netlist(
        pack="gates",
        library=dict(LIBRARY),
        cells={
            "a": _io("a", "IN", "y", "out"),
            "z": _io("z", "OUT", "a", "in"),
            "b": _io("b", "IN", "y", "out"),
            "y": _io("y", "OUT", "a", "in"),
            "d": _io("d", "IN", "y", "out"),
            "x": _io("x", "OUT", "a", "in"),
        },
        nets={
            "A": _net("A", "a", "z"),
            "B": _net("B", "b", "y"),
            "D": _net("D", "d", "x"),
        },
    )
    physics = GatesPhysics()
    physics.carriers = NoCrossings()
    router = DefaultRouter()
    router.costs = Costs(ripup=1)
    return World(problem(netlist, width=16, height=5), physics, router=router)


def test_a_displaced_net_never_displaces_a_third() -> None:
    world = _world()
    with world.transaction() as tx:
        assert world.place("b", 0, 1) is None and world.place("y", 15, 1) is None
        assert world.place("d", 0, 3) is None and world.place("x", 15, 3) is None
        assert world.place("a", 0, 0) is None
        before = world.digest()
        rows = {"B": 1, "D": 3}
        assert all(
            {c[1] for c in world.wires[n].cells()} == {row} for n, row in rows.items()
        )
        refusal = world.place("z", 15, 2)
        assert refusal is not None and refusal.stage == "route", refusal
        assert world.digest() == before
        assert "B" in world.wires and "D" in world.wires
        tx.commit()
