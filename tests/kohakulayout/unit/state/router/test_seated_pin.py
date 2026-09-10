"""A pin whose attach cell the net's own tree already crosses is seated there with a junction, no path searched."""

from fractions import Fraction

from kohakulayout.ir import Cell, Net, Netlist, Pin, PinRef
from kohakulayout.state import DefaultRouter, StateCheck, World
from kohakulayout.templates.physics.gates import LIBRARY, GatesPhysics, problem
from tests.kohakulayout.unit.state.router.test_terminal_crossing import _anchor
from tests.kohakulayout.unit.state.router.test_trees import UnitJunctions


def _io(cell_id: str, footprint: str, pin: str, direction: str) -> Cell:
    return Cell(
        id=cell_id,
        footprint=footprint,
        pins=(Pin(id=pin, direction=direction, carrier="wire", ports=(pin,)),),
    )


def _problem():
    netlist = Netlist(
        pack="gates",
        library=dict(LIBRARY),
        cells={
            "a": _io("a", "IN", "y", "out"),
            "o0": _io("o0", "OUT", "a", "in"),
            "o1": _io("o1", "OUT", "a", "in"),
        },
        nets={
            "n": Net(
                id="n",
                carrier="wire",
                rate=Fraction(1),
                sources=(PinRef(cell="a", pin="y"),),
                sinks=(PinRef(cell="o0", pin="a"), PinRef(cell="o1", pin="a")),
            )
        },
    )
    return problem(netlist, width=16, height=8)


def test_a_sink_on_the_trunk_is_seated_with_a_split() -> None:
    physics = GatesPhysics()
    physics.carriers = UnitJunctions()
    physics.unit_footprints = lambda: {
        "SPLIT": UnitJunctions.SPLIT,
        **GatesPhysics().unit_footprints(),
    }
    world = World(_problem(), physics, router=DefaultRouter())
    check = StateCheck().mount(world)
    with world.transaction() as tx:
        assert world.place("a", 0, 4) is None
        assert world.place("o0", 11, 4) is None
        assert {(1, 4), (10, 4)} <= world.wires["n"].cells()
        assert world.place("o1", *_anchor(world, "o1", (6, 4), (6, 5))) is None
        assert world.attach_cell("o1", "a") == (6, 4)
        tx.commit()
    wire = world.wires["n"]
    assert (6, 4) in wire.cells() and {(1, 4), (10, 4)} <= wire.cells()
    units = [world.units[u] for u in wire.units]
    assert [(u.footprint, u.x, u.y) for u in units] == [("SPLIT", 6, 4)]
    assert check.failures == []
