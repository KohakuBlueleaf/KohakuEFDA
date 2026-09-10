"""A pin that may use several ports is reached through whichever is open, the wire records the port it took, and two pins of one cell never take the same port; on both kernels alike."""

from fractions import Fraction

import pytest

from kohakulayout.engine import Budget, Context
from kohakulayout.ir import Cell, Footprint, Net, Netlist, Pin, PinRef, Port
from kohakulayout.state import DefaultRouter
from kohakulayout.templates.physics.gates import LIBRARY, problem

SINK = Footprint(
    id="SINK",
    width=1,
    height=3,
    ports=(
        Port(id="p0", side="W", offset=0, direction="in", carrier="wire"),
        Port(id="p1", side="W", offset=2, direction="in", carrier="wire"),
    ),
)
BLOCK = Footprint(id="BLOCK", width=1, height=1)
BAR = Footprint(id="BAR", width=1, height=3)


def _source(cell_id: str) -> Cell:
    return Cell(
        id=cell_id,
        footprint="IN",
        pins=(Pin(id="y", direction="out", carrier="wire", ports=("y",)),),
    )


def _net(net_id: str, source: str, pin: str) -> Net:
    return Net(
        id=net_id,
        carrier="wire",
        rate=Fraction(1),
        sources=(PinRef(cell=source, pin="y"),),
        sinks=(PinRef(cell="z", pin=pin),),
    )


def _problem(pins: tuple[str, ...]):
    netlist = Netlist(
        pack="gates",
        library={**LIBRARY, "SINK": SINK, "BLOCK": BLOCK, "BAR": BAR},
        cells={
            "z": Cell(
                id="z",
                footprint="SINK",
                pins=tuple(
                    Pin(id=pin, direction="in", carrier="wire", ports=("p0", "p1"))
                    for pin in pins
                ),
            ),
            "k": Cell(id="k", footprint="BLOCK"),
            "bar": Cell(id="bar", footprint="BAR"),
            **{f"b{i}": _source(f"b{i}") for i in range(len(pins))},
        },
        nets={f"n{i}": _net(f"n{i}", f"b{i}", pin) for i, pin in enumerate(pins)},
    )
    return problem(netlist, width=12, height=5)


def _world(pins: tuple[str, ...], kernel: str):
    ctx = Context(
        _problem(pins),
        physics=None,
        seed=1,
        budget=Budget(units=50),
        kernel=kernel,
        router=DefaultRouter(),
    )
    return ctx.world


@pytest.mark.parametrize("kernel", ["python", "native"])
def test_a_blocked_first_port_sends_the_wire_to_the_second(kernel: str) -> None:
    world = _world(("a",), kernel)
    with world.transaction() as tx:
        assert world.place("z", 8, 1) is None
        assert world.open_ports("z", "a") == (("p0", (7, 1)), ("p1", (7, 3)))
        assert world.place("k", 7, 1) is None
        assert world.open_ports("z", "a") == (("p0", (7, 1)), ("p1", (7, 3)))
        assert world.place("b0", 0, 2) is None
        wire = world.wires["n0"]
        assert wire.ports == {"z.a": "p1"}
        assert (7, 3) in wire.cells() and (7, 1) not in wire.cells()
        assert world.attach_cell("z", "a") == (7, 3)
        tx.commit()
    assert world.freeze().check_against(world.netlist, world.fabric) == []


@pytest.mark.parametrize("kernel", ["python", "native"])
def test_two_pins_of_one_cell_take_different_ports(kernel: str) -> None:
    world = _world(("a", "b"), kernel)
    with world.transaction() as tx:
        assert world.place("z", 8, 1) is None
        assert world.place("b0", 0, 0) is None
        assert world.wires["n0"].ports == {"z.a": "p0"}
        assert world.open_ports("z", "b") == (("p1", (7, 3)),)
        assert world.place("b1", 0, 4) is None
        assert world.wires["n1"].ports == {"z.b": "p1"}
        tx.commit()
    assert world.freeze().check_against(world.netlist, world.fabric) == []


def test_a_cell_may_cover_one_alternative_but_not_all() -> None:
    world = _world(("a",), "python")
    with world.transaction():
        assert world.place("z", 8, 1) is None
        refusal = world.place("bar", 7, 1)
        assert refusal is not None and refusal.stage == "port_shut", refusal
        assert "z.a" in refusal.detail
        assert world.place("k", 7, 1) is None
