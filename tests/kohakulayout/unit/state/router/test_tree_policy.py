"""A router's tree policy shapes the growth: which sink the trunk runs to, and which tree cells a join or a branch may leave from."""

from typing import Any

from kohakulayout.ir.geometry import XY
from kohakulayout.state import DefaultRouter, StateCheck, World
from kohakulayout.state.router.trees import TreePolicy
from kohakulayout.templates.physics.gates import GatesPhysics
from tests.kohakulayout.unit.state.router.test_trees import fanout_problem, place_all


class FarSinkFirst(TreePolicy):
    """The trunk runs to o1 (the far sink) first; a branch may only leave the trunk's first cell."""

    def trunk(self, world: Any, net: Any, root: Any, sinks: list[Any]) -> list[Any]:
        return [g for g in sinks if g[1] is not None and g[1].ref.cell == "o1"]

    def origins(
        self, world: Any, net: Any, plan, junctions, joinable, merging
    ) -> frozenset[XY]:
        return joinable & {plan.segments[0].cells[0]} if plan.segments else joinable


def test_the_policy_picks_the_trunk_and_the_branch_point() -> None:
    router = DefaultRouter()
    router.policy = FarSinkFirst()
    world = World(fanout_problem(), GatesPhysics(), router=router)
    check = StateCheck().mount(world)
    with world.transaction() as tx:
        assert world.place("a", 0, 3) is None
        assert world.place("o1", 11, 5) is None
        assert world.place("o0", 11, 1) is None
        tx.commit()
    wire = world.wires["n1"]
    trunk = wire.segments[0]
    assert trunk.cells[-1] == world.attach_cell("o1", "a")
    assert wire.segments[1].cells[0] == trunk.cells[0]
    assert check.failures == []


def test_the_default_policy_takes_the_nearest_sink() -> None:
    world = World(fanout_problem(), GatesPhysics(), router=DefaultRouter())
    place_all(world)
    trunk = world.wires["n1"].segments[0]
    assert trunk.cells[-1] in {
        world.attach_cell("o0", "a"),
        world.attach_cell("o1", "a"),
    }
