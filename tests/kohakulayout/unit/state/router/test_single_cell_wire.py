"""A wire whose two pins share one attach cell stands on that cell, crossing a foreign wire there with its unit when that wire runs straight through; a pin whose only cell a bending wire holds is shut."""

from fractions import Fraction

import pytest

from kohakulayout._rust import HAS_RUST
from kohakulayout.ir import Cell, Net, Netlist, Pin, PinRef
from kohakulayout.state import DefaultRouter, StateCheck, World
from kohakulayout.templates.physics.gates import LIBRARY, GatesPhysics, problem

KERNELS = ("python", "native") if HAS_RUST else ("python",)


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
            "b": _io("b", "IN", "y", "out"),
            "o1": _io("o1", "OUT", "a", "in"),
        },
        nets={
            "long": Net(
                id="long",
                carrier="wire",
                rate=Fraction(1),
                sources=(PinRef(cell="a", pin="y"),),
                sinks=(PinRef(cell="o0", pin="a"),),
            ),
            "short": Net(
                id="short",
                carrier="wire",
                rate=Fraction(1),
                sources=(PinRef(cell="b", pin="y"),),
                sinks=(PinRef(cell="o1", pin="a"),),
            ),
        },
    )
    return problem(netlist, width=16, height=8)


@pytest.mark.parametrize("kernel", KERNELS)
def test_a_single_cell_wire_crosses_a_straight_wire_with_its_unit(kernel: str) -> None:
    world = World(_problem(), GatesPhysics(), kernel=kernel, router=DefaultRouter())
    check = StateCheck().mount(world)
    with world.transaction() as tx:
        assert world.place("a", 5, 0) is None
        assert world.place("o0", 5, 7) is None
        assert (6, 3) in world.wires["long"].cells()
        assert world.place("b", 5, 3) is None
        assert world.place("o1", 7, 3) is None
        tx.commit()
    assert world.wires["short"].cells() == {(6, 3)}
    holders = set(world.kernel.holders_at("ground", (6, 3)))
    assert {"wire:long", "wire:short"} <= holders
    assert any(h.startswith("unit:") for h in holders)
    assert check.failures == []


@pytest.mark.parametrize("kernel", KERNELS)
def test_a_single_cell_wire_is_refused_where_the_foreign_wire_bends(
    kernel: str,
) -> None:
    world = World(_problem(), GatesPhysics(), kernel=kernel, router=DefaultRouter())
    with world.transaction() as tx:
        assert world.place("a", 5, 0) is None
        assert world.place("o0", 9, 5) is None
        cells = world.wires["long"].cells()
        bend = next(
            c
            for seg in world.wires["long"].segments
            for i, c in enumerate(seg.cells)
            if 0 < i < len(seg.cells) - 1
            and seg.cells[i - 1][0] != seg.cells[i + 1][0]
            and seg.cells[i - 1][1] != seg.cells[i + 1][1]
        )
        assert bend in cells
        refused = world.place("b", bend[0] - 1, bend[1])
        tx.commit()
    assert refused is not None and refused.stage == "port_shut"
