"""A net whose attach cell another wire took by rip-up never starts on top of it: it rips back or refuses."""

from fractions import Fraction

from kohakulayout.ir import Cell, Net, Netlist, Pin, PinRef
from kohakulayout.physics import CrossingRule
from kohakulayout.state import DefaultRouter, StateCheck, World
from kohakulayout.state.router.protocol import Costs
from kohakulayout.templates.physics.gates import LIBRARY, GatesPhysics, problem
from kohakulayout.templates.physics.gates.carriers import GatesCarriers


class NoCrossings(GatesCarriers):
    def crossing(self, a: str, b: str) -> CrossingRule:
        return CrossingRule(mode="forbidden")


def _problem():
    def io(cell_id: str, footprint: str, pin: str, direction: str) -> Cell:
        return Cell(
            id=cell_id,
            footprint=footprint,
            pins=(Pin(id=pin, direction=direction, carrier="wire", ports=(pin,)),),
        )

    netlist = Netlist(
        pack="gates",
        library=dict(LIBRARY),
        cells={
            "a": io("a", "IN", "y", "out"),
            "o0": io("o0", "OUT", "a", "in"),
            "b": io("b", "IN", "y", "out"),
            "o1": io("o1", "OUT", "a", "in"),
        },
        nets={
            "first": Net(
                id="first",
                carrier="wire",
                rate=Fraction(1),
                sources=(PinRef(cell="a", pin="y"),),
                sinks=(PinRef(cell="o0", pin="a"),),
            ),
            "second": Net(
                id="second",
                carrier="wire",
                rate=Fraction(1),
                sources=(PinRef(cell="b", pin="y"),),
                sinks=(PinRef(cell="o1", pin="a"),),
            ),
        },
    )
    return problem(netlist, width=16, height=8)


def test_a_ripped_attach_cell_is_never_shared() -> None:
    physics = GatesPhysics()
    physics.carriers = NoCrossings()
    router = DefaultRouter()
    router.costs = Costs(ripup=1)
    world = World(_problem(), physics, router=router)
    check = StateCheck().mount(world)
    with world.transaction() as tx:
        assert world.place("b", 5, 5, 270) is None
        assert world.attach_cell("b", "y") == (5, 4)
        assert world.place("o1", 6, 1) is None
        assert "second" in world.wires
        assert world.place("a", 0, 4) is None
        assert world.place("o0", 11, 4) is None
        tx.commit()
    assert {"first", "second"} <= set(world.wires)
    holders = world.kernel.holders_at("ground", (5, 4))
    assert "wire:second" in holders and "wire:first" not in holders
    assert check.failures == []
