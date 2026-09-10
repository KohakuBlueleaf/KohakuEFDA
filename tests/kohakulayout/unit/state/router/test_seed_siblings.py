"""A seeded grow seats one pin per tree end: sibling pins sharing their ports never share one, through a partial rip and even when the standing wire had not reached one of them."""

from fractions import Fraction

from kohakulayout.ir import Cell, Footprint, Net, Netlist, Pin, PinRef, Port
from kohakulayout.ir.layout import Layout, Wire
from kohakulayout.state import DefaultRouter, StateCheck, World
from kohakulayout.templates.physics.gates import LIBRARY, GatesPhysics, problem

TRI = Footprint(
    id="TRI",
    width=1,
    height=3,
    ports=tuple(
        Port(id=f"p{i}", side="E", offset=i, direction="out", carrier="wire")
        for i in range(3)
    ),
)


def _problem():
    ports = ("p0", "p1", "p2")
    netlist = Netlist(
        pack="gates",
        library={**LIBRARY, TRI.id: TRI},
        cells={
            "s": Cell(
                id="s",
                footprint="TRI",
                pins=(
                    Pin(id="y0", direction="out", carrier="wire", ports=ports),
                    Pin(id="y1", direction="out", carrier="wire", ports=ports),
                ),
            ),
            "o0": _out("o0"),
            "o1": _out("o1"),
            "k": Cell(id="k", footprint="TRI"),
        },
        nets={
            "n": Net(
                id="n",
                carrier="wire",
                rate=Fraction(1),
                sources=(PinRef(cell="s", pin="y0"), PinRef(cell="s", pin="y1")),
                sinks=(PinRef(cell="o0", pin="a"), PinRef(cell="o1", pin="a")),
            )
        },
    )
    return problem(netlist, width=20, height=10)


def _out(cell_id: str) -> Cell:
    return Cell(
        id=cell_id,
        footprint="OUT",
        pins=(Pin(id="a", direction="in", carrier="wire", ports=("a",)),),
    )


def test_siblings_keep_distinct_ports_through_a_partial_rip() -> None:
    world = World(_problem(), GatesPhysics(), router=DefaultRouter())
    check = StateCheck().mount(world)
    with world.transaction() as tx:
        assert world.place("s", 0, 3) is None
        assert world.place("o0", 17, 4) is None
        assert world.place("o1", 12, 9) is None
        wire = world.wires["n"]
        before = dict(wire.ports)
        assert len(set(before.values())) == 2
        branch = next(seg for seg in wire.segments[1:] if (11, 9) in seg.cells)
        assert world.place("k", 11, 5) is None
        tx.commit()
    wire = world.wires["n"]
    assert wire.segments[0].cells == world.wires["n"].segments[0].cells
    assert branch not in wire.segments
    assert wire.ports == before
    assert len(set(wire.ports.values())) == 2
    assert check.failures == []


def test_a_sibling_the_standing_wire_missed_takes_a_port_of_its_own() -> None:
    world = World(_problem(), GatesPhysics(), router=DefaultRouter())
    with world.transaction() as tx:
        assert world.place("s", 0, 3) is None
        assert world.place("o0", 17, 4) is None
        assert world.place("o1", 12, 9) is None
        tx.commit()
    wire = world.wires["n"]
    trunk, branch = wire.segments[0], next(
        seg for seg in wire.segments[1:] if (11, 9) in seg.cells
    )
    missed = Wire(net="n", segments=(trunk, branch), ports={"s.y0": "p1"})
    world.load(
        Layout(
            placements=dict(world.placements),
            wires={"n": missed},
            units=dict(world.units),
        )
    )
    check = StateCheck().mount(world)
    with world.transaction() as tx:
        assert world.place("k", 11, 5) is None
        tx.commit()
    ports = world.wires["n"].ports
    assert ports["s.y0"] == "p1"
    assert ports["s.y1"] != "p1"
    assert check.failures == []
