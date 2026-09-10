"""A footprint may displace a route unit or a field emitter: the net routes again, the emitter moves."""

from fractions import Fraction

from kohakulayout.ir import Cell, Footprint, Net, Netlist, PinRef
from kohakulayout.state import DefaultRouter, StateCheck, World
from kohakulayout.templates.physics.gates import (
    LIBRARY,
    GatesPhysics,
    GatesPowerPhysics,
    problem,
)
from tests.kohakulayout.unit.state.router.test_trees import UnitJunctions, place_all
from tests.kohakulayout.unit.state.test_emitter_displacement import _problem

BLOCK = Footprint(id="BLOCK", width=1, height=1)


def _emitters(world) -> dict[str, tuple[int, int]]:
    return {
        uid: (u.x, u.y)
        for uid, u in world.units.items()
        if u.owner.startswith("field:")
    }


def test_a_footprint_over_a_junction_rips_the_net_which_routes_again() -> None:
    physics = GatesPhysics()
    physics.carriers = UnitJunctions()
    physics.unit_footprints = lambda: {
        "SPLIT": UnitJunctions.SPLIT,
        **GatesPhysics().unit_footprints(),
    }
    cells = {
        "a": Cell(id="a", kind="IN", footprint="IN"),
        "o0": Cell(id="o0", kind="OUT", footprint="OUT"),
        "o1": Cell(id="o1", kind="OUT", footprint="OUT"),
        "k": Cell(id="k", footprint="BLOCK"),
    }
    nets = {
        "n1": Net(
            id="n1",
            carrier="wire",
            rate=Fraction(1),
            sources=(PinRef(cell="a", pin="y"),),
            sinks=(PinRef(cell="o0", pin="a"), PinRef(cell="o1", pin="a")),
        )
    }
    fanout = problem(
        Netlist(
            pack="gates", library={**LIBRARY, "BLOCK": BLOCK}, cells=cells, nets=nets
        ),
        width=12,
        height=8,
    )
    world = World(fanout, physics, router=DefaultRouter())
    check = StateCheck().mount(world)
    place_all(world)
    (split_id,) = world.wires["n1"].units
    split = world.units[split_id]
    with world.transaction() as tx:
        assert world.place("k", split.x, split.y, 0) is None
        assert split_id not in world.units
        wire = world.wires["n1"]
        assert (split.x, split.y) not in wire.cells()
        assert {(10, 1), (10, 5)} <= wire.cells()
        tx.commit()
    assert check.failures == []


def test_a_footprint_over_an_emitter_moves_it_and_keeps_the_gate_covered() -> None:
    netlist = _problem().netlist
    netlist.library["BLOCK"] = BLOCK
    netlist.cells["k"] = Cell(id="k", footprint="BLOCK")
    powered = problem(netlist, power=True, width=16, height=10)
    world = World(powered, GatesPowerPhysics())
    check = StateCheck().mount(world)
    with world.transaction() as tx:
        assert world.place("g", 6, 3, 0) is None
        ((emitter, spot),) = _emitters(world).items()
        assert world.place("k", spot[0], spot[1], 0) is None
        assert emitter not in world.units
        after = _emitters(world)
        assert len(after) == 1 and spot not in after.values()
        assert tuple(world.kernel.holders_at("ground", spot)) == ("cell:k",)
        covered = world.field_coverage("power")
        assert any(c in covered for c in ((6, 3), (7, 3), (6, 5), (7, 5)))
        tx.commit()
    assert check.failures == []
