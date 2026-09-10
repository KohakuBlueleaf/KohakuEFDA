"""A seeded grow reads a join segment tree-ward: a branch leaving a joined source's attach cell needs a split there."""

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
            "b": _io("b", "IN", "y", "out"),
            "o0": _io("o0", "OUT", "a", "in"),
            "o1": _io("o1", "OUT", "a", "in"),
        },
        nets={
            "n": Net(
                id="n",
                carrier="wire",
                rate=Fraction(1),
                sources=(PinRef(cell="a", pin="y"), PinRef(cell="b", pin="y")),
                sinks=(PinRef(cell="o0", pin="a"), PinRef(cell="o1", pin="a")),
            )
        },
    )
    return problem(netlist, width=16, height=8)


def test_a_branch_off_a_joined_source_gets_a_split() -> None:
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
        assert world.place("b", *_anchor(world, "b", (6, 2), (6, 1))) is None
        assert world.place("o1", *_anchor(world, "o1", (6, 6), (6, 7))) is None
        tx.commit()
    wire = world.wires["n"]
    joined = world.attach_cell("b", "y")
    starts = [seg for seg in wire.segments[1:] if seg.cells[0] == joined]
    if starts:
        units = {
            (world.units[u].x, world.units[u].y): world.units[u].footprint
            for u in wire.units
        }
        assert units.get(joined) == "SPLIT"
    assert check.failures == []
