"""Trees: fan-out nets grow nearest-first, junctions follow the pack's rule."""

import pytest

from kohakulayout.ir import Cell, Footprint, Net, Netlist, PinRef, Refusal
from kohakulayout.physics import JunctionRule
from kohakulayout.state import DefaultRouter, StateCheck, World
from kohakulayout.templates.physics.gates import LIBRARY, GatesPhysics, problem
from kohakulayout.templates.physics.gates.carriers import GatesCarriers


def fanout_problem():
    cells = {
        "a": Cell(id="a", kind="IN", footprint="IN"),
        "o0": Cell(id="o0", kind="OUT", footprint="OUT"),
        "o1": Cell(id="o1", kind="OUT", footprint="OUT"),
    }
    nets = {
        "n1": Net(
            id="n1",
            carrier="wire",
            sources=(PinRef(cell="a", pin="y"),),
            sinks=(PinRef(cell="o0", pin="a"), PinRef(cell="o1", pin="a")),
        )
    }
    return problem(
        Netlist(pack="gates", library=dict(LIBRARY), cells=cells, nets=nets),
        width=12,
        height=8,
    )


def place_all(world: World) -> None:
    with world.transaction() as tx:
        assert world.place("a", 0, 3) is None
        assert world.place("o0", 11, 1) is None
        assert world.place("o1", 11, 5) is None
        tx.commit()


class UnitJunctions(GatesCarriers):
    SPLIT = Footprint(id="SPLIT", width=1, height=1, rotations=(0,))

    def junction(self, carrier: str) -> JunctionRule:
        return JunctionRule(mode="unit", split=self.SPLIT, merge=self.SPLIT)

    def may_share(self, a, b) -> bool:
        if {a.kind, b.kind} == {"wire", "unit"} and self.SPLIT.id in (
            a.unit_kind,
            b.unit_kind,
        ):
            return True
        return super().may_share(a, b)


class NoJunctions(GatesCarriers):
    def junction(self, carrier: str) -> JunctionRule:
        return JunctionRule(mode="forbidden")


def test_free_junctions_share_the_trunk() -> None:
    world = World(fanout_problem(), GatesPhysics(), router=DefaultRouter())
    check = StateCheck().mount(world)
    place_all(world)
    wire = world.wires["n1"]
    assert len(wire.segments) == 2
    assert wire.segments[0].cells[0] == (1, 3)
    assert {(10, 1), (10, 5)} <= wire.cells()
    assert wire.units == ()
    assert check.failures == []


def test_unit_junctions_place_a_split() -> None:
    physics = GatesPhysics()
    physics.carriers = UnitJunctions()
    physics.unit_footprints = lambda: {
        "SPLIT": UnitJunctions.SPLIT,
        **GatesPhysics().unit_footprints(),
    }
    world = World(fanout_problem(), physics, router=DefaultRouter())
    check = StateCheck().mount(world)
    place_all(world)
    wire = world.wires["n1"]
    assert len(wire.units) == 1
    unit = world.units[wire.units[0]]
    assert unit.kind == "SPLIT" and (unit.x, unit.y) in wire.cells()
    assert check.failures == []


def test_forbidden_junctions_refuse_fanout() -> None:
    physics = GatesPhysics()
    physics.carriers = NoJunctions()
    world = World(fanout_problem(), physics, router=DefaultRouter())
    with world.transaction():
        assert world.place("a", 0, 3) is None
        assert world.place("o0", 11, 1) is None
        refusal = world.place("o1", 11, 5)
    assert isinstance(refusal, Refusal) and refusal.stage == "route"
    assert "junction" in refusal.detail
    with pytest.raises(KeyError):
        world.placements["o1"]


def merge_split_problem():
    cells = {
        "a": Cell(id="a", kind="IN", footprint="IN"),
        "b": Cell(id="b", kind="IN", footprint="IN"),
        "o0": Cell(id="o0", kind="OUT", footprint="OUT"),
        "o1": Cell(id="o1", kind="OUT", footprint="OUT"),
    }
    nets = {
        "n": Net(
            id="n",
            carrier="wire",
            sources=(PinRef(cell="a", pin="y"), PinRef(cell="b", pin="y")),
            sinks=(PinRef(cell="o0", pin="a"), PinRef(cell="o1", pin="a")),
        )
    }
    return problem(
        Netlist(pack="gates", library=dict(LIBRARY), cells=cells, nets=nets),
        width=14,
        height=8,
    )


def test_a_trunk_reaches_a_sink_first_then_sources_merge_and_sinks_split() -> None:
    physics = GatesPhysics()
    physics.carriers = UnitJunctions()
    physics.unit_footprints = lambda: {
        "SPLIT": UnitJunctions.SPLIT,
        **GatesPhysics().unit_footprints(),
    }
    world = World(merge_split_problem(), physics, router=DefaultRouter())
    check = StateCheck().mount(world)
    with world.transaction() as tx:
        assert world.place("a", 0, 1) is None
        assert world.place("b", 0, 5) is None
        assert world.place("o0", 13, 1) is None
        assert world.place("o1", 13, 5) is None
        tx.commit()
    wire = world.wires["n"]
    assert len(wire.segments) == 3
    trunk = wire.segments[0].cells
    assert trunk[0] == world.attach_cell("a", "y")
    assert trunk[-1] in (world.attach_cell("o0", "a"), world.attach_cell("o1", "a"))
    assert wire.segments[1].cells[-1] == world.attach_cell("b", "y")
    spots = [(world.units[u].x, world.units[u].y) for u in wire.units]
    assert len(spots) == 2 and len(set(spots)) == 2
    assert wire.segments[1].cells[0] in spots and wire.segments[2].cells[0] in spots
    assert check.failures == []
