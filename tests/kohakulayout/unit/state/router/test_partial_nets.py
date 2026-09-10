"""A net routes between the pins that stand and grows when another lands; nothing routes before a source and a sink are placed."""

from kohakulayout.state import DefaultRouter, StateCheck, World
from kohakulayout.templates.physics.gates import GatesPhysics
from tests.kohakulayout.unit.state.router.test_trees import fanout_problem


def test_a_net_routes_early_and_grows_to_each_new_pin() -> None:
    world = World(fanout_problem(), GatesPhysics(), router=DefaultRouter())
    check = StateCheck().mount(world)
    with world.transaction() as tx:
        assert world.place("o0", 11, 1) is None
        assert "n1" not in world.wires
        assert world.place("a", 0, 3) is None
        first = world.wires["n1"]
        assert (1, 3) in first.cells() and (10, 1) in first.cells()
        assert (10, 5) not in first.cells()
        assert world.place("o1", 11, 5) is None
        grown = world.wires["n1"]
        assert {(1, 3), (10, 1), (10, 5)} <= grown.cells()
        tx.commit()
    assert check.failures == []
    assert world.freeze().check_against(world.netlist, world.fabric) == []
