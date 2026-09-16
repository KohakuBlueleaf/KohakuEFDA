"""The lane router lays a net as pin-to-pin lanes: port to port when neither pin has a lane, else from the source pin's own lanes to the sink pin's."""

from typing import Any

from kohakulayout.ir import Cell, Net, Netlist, PinRef, Segment, Wire
from kohakulayout.state import LaneRouter, StateCheck, World
from kohakulayout.state.router.lanes import attach_pins, lane_pins
from kohakulayout.state.router.protocol import terminals
from kohakulayout.state.router.trees import TreePolicy
from kohakulayout.templates.physics.gates import (
    LIBRARY,
    GatesPhysics,
    from_expressions,
    problem,
)

A0, A1 = PinRef(cell="a0", pin="y"), PinRef(cell="a1", pin="y")
O0, O1 = PinRef(cell="o0", pin="a"), PinRef(cell="o1", pin="a")


def two_by_two():
    cells = {
        "a0": Cell(id="a0", kind="IN", footprint="IN"),
        "a1": Cell(id="a1", kind="IN", footprint="IN"),
        "o0": Cell(id="o0", kind="OUT", footprint="OUT"),
        "o1": Cell(id="o1", kind="OUT", footprint="OUT"),
    }
    nets = {"n1": Net(id="n1", carrier="wire", sources=(A0, A1), sinks=(O0, O1))}
    return problem(
        Netlist(pack="gates", library=dict(LIBRARY), cells=cells, nets=nets),
        width=12,
        height=8,
    )


class ThreeLanes(TreePolicy):
    def lanes(self, world: Any, net: Any) -> list[tuple[Any, Any]]:
        return [(A0, O0), (A1, O1), (A0, O1)]


def lane_world() -> tuple[World, StateCheck]:
    router = LaneRouter(max_rips=0)
    router.policy = ThreeLanes()
    world = World(two_by_two(), GatesPhysics(), router=router)
    return world, StateCheck().mount(world)


def test_two_lanes_apart_then_a_lane_between_them() -> None:
    world, check = lane_world()
    with world.transaction() as tx:
        assert world.place("a0", 0, 1) is None
        assert world.place("a1", 0, 6) is None
        assert "n1" not in world.wires
        assert world.place("o0", 11, 1) is None
        assert [len(s.cells) for s in world.wires["n1"].segments] == [10]
        assert world.place("o1", 11, 6) is None
        tx.commit()
    first, second, third = world.wires["n1"].segments
    assert first.cells[0] == world.attach_cell("a0", "y")
    assert first.cells[-1] == world.attach_cell("o0", "a")
    assert second.cells[0] == world.attach_cell("a1", "y")
    assert second.cells[-1] == world.attach_cell("o1", "a")
    assert third.cells[0] in first.cells and third.cells[0] != first.cells[-1]
    assert third.cells[-1] in second.cells and third.cells[-1] != second.cells[-1]
    assert check.failures == []


def test_standing_lanes_are_read_back_to_their_pins() -> None:
    world, _ = lane_world()
    with world.transaction() as tx:
        for cell_id, x, y in (("a0", 0, 1), ("o0", 11, 1), ("a1", 0, 6), ("o1", 11, 6)):
            assert world.place(cell_id, x, y) is None
        tx.commit()
    net = world.netlist.nets["n1"]
    wire = world.wires["n1"]
    at = attach_pins(terminals(world, net), wire.ports)
    assert lane_pins(list(wire.segments), at, frozenset(net.sources)) == [
        (A0, O0),
        (A1, O1),
        (A0, O1),
    ]


class CrossedLanes(TreePolicy):
    def lanes(self, world: Any, net: Any) -> list[tuple[Any, Any]]:
        return [(A0, O0), (A1, O1)]


def test_a_lane_crosses_another_lane_of_its_own_net_with_the_carriers_unit() -> None:
    router = LaneRouter(max_rips=0)
    router.policy = CrossedLanes()
    world = World(two_by_two(), GatesPhysics(), router=router)
    check = StateCheck().mount(world)
    with world.transaction() as tx:
        for cell_id, x, y in (("a0", 5, 0), ("o0", 5, 7), ("a1", 0, 3), ("o1", 11, 3)):
            assert world.place(cell_id, x, y) is None
        tx.commit()
    wire = world.wires["n1"]
    first, second = wire.segments
    shared = set(first.cells) & set(second.cells)
    assert len(shared) == 1
    rule = world.physics.carriers.crossing("wire", "wire")
    units = [world.units[u] for u in wire.units]
    assert [(u.x, u.y) for u in units if u.footprint == rule.unit.id] == [min(shared)]
    assert check.failures == []


def test_a_lane_never_ends_on_its_own_source_trunk() -> None:
    """The trunk to the first sink runs over the second sink's only attach cell; the lane to the second sink is refused rather than ending on the trunk without a junction (a standing trunk by the attach tables, one laid in the same plan by the lane router's own rule)."""
    world = World(
        problem(from_expressions(["y = a & b", "z = a & c"]), width=16, height=8),
        GatesPhysics(),
        router=LaneRouter(max_rips=0),
    )
    check = StateCheck().mount(world)
    with world.transaction() as tx:
        for cell_id, x, y in (
            ("a", 0, 1),
            ("b", 0, 0),
            ("c", 0, 7),
            ("g1", 12, 0),
            ("g2", 6, 3),
        ):
            assert world.place(cell_id, x, y) is None
        tx.commit()
    assert world.attach_cells("g2")["a"] == (5, 3)
    trunk = [
        (1, 1),
        (2, 1),
        (3, 1),
        (4, 1),
        (4, 2),
        (4, 3),
        (5, 3),
        (5, 2),
        (5, 1),
        *((x, 1) for x in range(6, 12)),
        (11, 0),
    ]
    layer = world.carrier_layer("wire")
    with world.transaction() as tx:
        for net_id in list(world.wires):
            world.unroute(net_id)
        world.set_wire(
            Wire(
                net="n1",
                segments=(Segment(carrier="wire", layer=layer, cells=tuple(trunk)),),
            )
        )
        refusal = world.route("n1", grow=True)
        tx.commit()
    assert refusal is not None and refusal.stage == "route"
    ends = [tuple(seg.cells[-1]) for seg in world.wires["n1"].segments]
    assert (5, 3) not in ends[1:] and len(world.wires["n1"].segments) == 1
    assert check.failures == []
