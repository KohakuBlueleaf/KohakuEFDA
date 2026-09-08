"""Level 1 on gates: the facts of the pack as encoded, the synth by seed, the fixture."""

from importlib.resources import files

import pytest

from kohakulayout.ir import Netlist, Placement
from kohakulayout.physics import Occupant, get
from kohakulayout.state import World
from kohakulayout.templates.physics.gates import (
    LIBRARY,
    GatesPhysics,
    from_expressions,
    problem,
    random_circuit,
)
from kohakulayout.templates.physics.gates.library import FANOUT_LIMIT, JUMPER
from kohakulayout.templates.physics.gates.synth import SynthError


def test_library_shapes_and_ports() -> None:
    for gate in ("AND", "OR", "XOR"):
        fp = LIBRARY[gate]
        assert (fp.width, fp.height) == (3, 3)
        assert [(p.id, p.side, p.offset) for p in fp.ports] == [
            ("a", "W", 0),
            ("b", "W", 2),
            ("y", "E", 1),
        ]
    for gate in ("NOT", "BUF"):
        assert (LIBRARY[gate].width, LIBRARY[gate].height) == (2, 3)
    dff = LIBRARY["DFF"]
    assert dff.port("clk").carrier == "clk" and dff.port("clk").side == "S"
    assert LIBRARY["IN"].port("y").side == "E" and LIBRARY["OUT"].port("a").side == "W"
    assert JUMPER.rotations == (0,)


def test_fabric_and_registration() -> None:
    physics = get("gates@1")
    assert isinstance(physics, GatesPhysics)
    fabric = physics.fabric({"width": 20, "height": 10})
    assert fabric.layers == ("ground", "overhead")
    assert fabric.carriers["clk"].layer == "overhead"
    assert fabric.entries == ("W", "E")
    assert len(fabric.regions["build"].cells()) == 200
    assert "JUMPER" in physics.unit_footprints()


def test_carrier_rules() -> None:
    carriers = GatesPhysics().carriers
    wire, clk = Occupant(kind="wire", carrier="wire"), Occupant(
        kind="wire", carrier="clk"
    )
    assert carriers.may_share(wire, clk) and not carriers.may_share(wire, wire)
    assert carriers.may_share(wire, Occupant(kind="unit", unit_kind="JUMPER"))
    assert not carriers.may_share(wire, Occupant(kind="cell"))
    assert carriers.crossing("wire", "wire").unit is JUMPER
    assert carriers.crossing("clk", "clk").mode == "forbidden"
    assert carriers.crossing("wire", "clk").mode == "free"
    assert carriers.junction("wire").mode == "free"
    assert carriers.transfers_through(
        "JUMPER", "wire"
    ) and not carriers.transfers_through("JUMPER", "clk")


def test_edge_anchors_and_legal() -> None:
    netlist = from_expressions("y = a & b")
    world = World(problem(netlist, width=16, height=8), GatesPhysics())
    anchors = list(world.anchors("a"))
    assert all(a.x == 0 for a in anchors) and len(anchors) == 8 * 4
    outs = list(world.anchors("y"))
    assert all(a.x == 15 for a in outs)
    gates = list(world.anchors("g1"))
    assert len(gates) == 14 * 6 * 4
    refusal = world.physics.boundaries.legal(
        world, Placement(cell="a", x=3, y=0, rot=0)
    )
    assert refusal.stage == "legal" and "W edge" in refusal.detail
    assert (
        world.physics.boundaries.legal(world, Placement(cell="g1", x=3, y=0, rot=0))
        is None
    )


def test_synth_expressions() -> None:
    netlist = from_expressions(["s = a ^ b", "c = a & b", "z = ~(s | c)"])
    assert netlist.check() == []
    assert {c.footprint for c in netlist.cells.values()} == {
        "IN",
        "OUT",
        "XOR",
        "AND",
        "OR",
        "NOT",
    }
    assert netlist.cells["a"].constraint.attrs == {"gates": {"side": "W"}}
    assert netlist.cells["z"].constraint.attrs == {"gates": {"side": "E"}}
    fanout = {
        src.cell: len(net.sinks) for net in netlist.nets.values() for src in net.sources
    }
    assert fanout["a"] == 2 and fanout["b"] == 2
    with pytest.raises(SynthError):
        from_expressions("y = a &")
    with pytest.raises(SynthError):
        from_expressions("a & b")
    assert from_expressions("y = a").cells["g1"].footprint == "BUF"


def test_random_circuit_is_reproducible() -> None:
    one, two = random_circuit(7, inputs=3, gates=10), random_circuit(
        7, inputs=3, gates=10
    )
    assert one.digest() == two.digest()
    assert one.digest() != random_circuit(8, inputs=3, gates=10).digest()
    assert one.check() == []
    assert sum(1 for c in one.cells.values() if c.footprint == "IN") == 3
    assert all(net.sinks for net in one.nets.values())
    assert len(random_circuit(1, gates=40).cells) > 40


def test_fanout_rule_finds_a_wide_net() -> None:
    lines = [f"o{i} = a & b{i}" for i in range(FANOUT_LIMIT + 1)]
    netlist = from_expressions(lines)
    world = World(problem(netlist), GatesPhysics())
    findings = [
        f for rule in world.physics.rules for f in rule.check(world, world.freeze(), {})
    ]
    assert [f.rule for f in findings] == ["gates.fanout"]
    assert findings[0].attrs["gates"]["sinks"] == FANOUT_LIMIT + 1


def test_fixture_parses_and_verifies() -> None:
    text = (
        files("kohakulayout.templates.physics.gates")
        .joinpath("fixtures/and_or_not.kl")
        .read_text()
    )
    netlist = Netlist.parse(text)
    netlist.verify()
    assert sorted(netlist.cells) == ["a", "b", "c", "g1", "g2", "g3", "y"]
    assert netlist.library["NOT"].model_dump() == LIBRARY["NOT"].model_dump()
