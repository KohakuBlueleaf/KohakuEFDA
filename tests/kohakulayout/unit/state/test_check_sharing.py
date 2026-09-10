"""The state checker reports two wires on one cell unless the pack lets their carriers share it."""

from fractions import Fraction

from kohakulayout.engine import Budget, Context
from kohakulayout.ir import Cell, Net, Netlist, Pin, PinRef, Segment, Wire
from kohakulayout.state import StateCheck
from kohakulayout.templates.physics.gates import LIBRARY, problem


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


def test_two_wires_on_one_cell_fail_the_check() -> None:
    ctx = Context(_problem(), physics=None, seed=1, budget=Budget(units=50))
    world = ctx.world
    check = StateCheck(strict=False).mount(world)
    with world.transaction() as tx:
        assert world.place("a", 0, 3) is None
        assert world.place("o0", 11, 3) is None
        tx.commit()
    assert check.failures == []
    taken = next(iter(world.wires["first"].segments)).cells[1]
    with world.transaction() as tx:
        world.set_wire(
            Wire(
                net="second",
                segments=(Segment(carrier="wire", layer="ground", cells=(taken,)),),
            )
        )
        tx.commit()
    check.holders(world)
    assert any("share" in failure for failure in check.failures)
