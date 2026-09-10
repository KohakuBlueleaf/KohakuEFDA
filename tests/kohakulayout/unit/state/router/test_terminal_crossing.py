"""A path may start or end on a cell another wire runs straight through: the pin is not shut and the route crosses there."""

from fractions import Fraction

import pytest

from kohakulayout._rust import HAS_RUST
from kohakulayout.ir import Cell, Net, Netlist, Pin, PinRef
from kohakulayout.ir.geometry import ROTATIONS
from kohakulayout.physics import CrossingRule
from kohakulayout.state import DefaultRouter, StateCheck, World
from kohakulayout.state.attach import options_at
from kohakulayout.templates.physics.gates import LIBRARY, GatesPhysics, problem
from kohakulayout.templates.physics.gates.carriers import GatesCarriers
from kohakulayout.templates.physics.gates.library import JUMPER

KERNELS = ("python", "native") if HAS_RUST else ("python",)


class NoCrossings(GatesCarriers):
    def crossing(self, a: str, b: str) -> CrossingRule:
        return CrossingRule(mode="forbidden")


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


def _anchor(world: World, cell_id: str, attach, port) -> tuple[int, int, int]:
    """An anchor whose only pin attaches at ``attach`` from the port cell ``port``."""
    fp = world.footprint_of(cell_id)
    (pin,) = world.netlist.pins_of(cell_id)
    for rot in ROTATIONS:
        for x in range(world.fabric.width):
            for y in range(world.fabric.height):
                for _, xy, port_xy in options_at(fp, pin, x, y, rot):
                    if xy == attach and port_xy == port:
                        return x, y, rot
    raise AssertionError(f"no anchor of {cell_id} attaches at {attach}")


def _world(kernel: str, carriers=None) -> tuple[World, StateCheck]:
    physics = GatesPhysics()
    if carriers is not None:
        physics.carriers = carriers
    world = World(_problem(), physics, kernel=kernel, router=DefaultRouter())
    check = StateCheck().mount(world)
    with world.transaction() as tx:
        assert world.place("a", 0, 4) is None
        assert world.place("o0", 11, 4) is None
        tx.commit()
    assert {(1, 4), (10, 4)} <= world.wires["first"].cells()
    return world, check


def _crossed(world: World, cell) -> None:
    holders = set(world.kernel.holders_at("ground", cell))
    units = [h for h in holders if h.startswith("unit:")]
    assert {"wire:first", "wire:second"} <= holders and len(units) == 1
    unit = world.units[units[0].split(":", 1)[1]]
    assert unit.footprint == JUMPER.id and unit.owner == "net:second"
    assert cell in world.wires["second"].cells()
    assert {(1, 4), (10, 4)} <= world.wires["first"].cells()


@pytest.mark.parametrize("kernel", KERNELS)
def test_a_source_leaves_across_the_wire_on_its_attach_cell(kernel: str) -> None:
    world, check = _world(kernel)
    with world.transaction() as tx:
        assert world.place("b", *_anchor(world, "b", (5, 4), (5, 5))) is None
        assert world.place("o1", *_anchor(world, "o1", (5, 1), (6, 1))) is None
        tx.commit()
    _crossed(world, (5, 4))
    assert world.wires["second"].cells() >= {(5, 4), (5, 3), (5, 2), (5, 1)}
    assert check.failures == []


@pytest.mark.parametrize("kernel", KERNELS)
def test_a_sink_is_reached_across_the_wire_on_its_attach_cell(kernel: str) -> None:
    world, check = _world(kernel)
    with world.transaction() as tx:
        assert world.place("b", *_anchor(world, "b", (7, 1), (7, 0))) is None
        assert world.place("o1", *_anchor(world, "o1", (7, 4), (7, 5))) is None
        tx.commit()
    _crossed(world, (7, 4))
    assert world.wires["second"].cells() >= {(7, 1), (7, 2), (7, 3), (7, 4)}
    assert check.failures == []


@pytest.mark.parametrize("kernel", KERNELS)
def test_a_forbidden_crossing_keeps_the_attach_cell_shut(kernel: str) -> None:
    world, check = _world(kernel, NoCrossings())
    with world.transaction() as tx:
        refusal = world.place("b", *_anchor(world, "b", (5, 4), (5, 5)))
        assert refusal is not None and refusal.stage == "port_shut"
        tx.commit()
    assert check.failures == []
