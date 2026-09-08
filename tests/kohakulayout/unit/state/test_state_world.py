"""Level 2 on the null pack: the world's obligations, driven with the checker mounted."""

import pytest

from kohakulayout.errors import StateError
from kohakulayout.ir import Netlist, Problem, Refusal, Segment, Wire
from kohakulayout.physics import Emitter, GreedyCover, Reach, UnitPlacement, get
from kohakulayout.physics.protocol import Occupant
from kohakulayout.state import PyKernel, StateCheck, World
from kohakulayout.templates.physics.null import LIBRARY, NullPhysics
from kohakulayout.templates.physics.null import problem as null_problem


def test_mutation_outside_a_transaction_is_refused(null_world: World) -> None:
    with pytest.raises(StateError, match="outside a transaction"):
        null_world.place("box", 0, 0)
    assert null_world.placements == {}


def test_transaction_rolls_back_unless_committed(
    null_world: World, state_check: StateCheck
) -> None:
    before = null_world.digest()
    with null_world.transaction():
        assert null_world.place("box", 1, 1) is None
        assert null_world.placements["box"].x == 1
    assert null_world.digest() == before
    assert null_world.kernel.free_for("ground", [(1, 1), (2, 2)])
    with null_world.transaction() as tx:
        null_world.place("box", 1, 1)
        tx.commit()
    assert null_world.digest() != before
    assert null_world.kernel.holders_at("ground", (2, 2)) == ("cell:box",)


def test_refusals_name_a_stage_and_leave_the_digest(
    null_world: World, state_check: StateCheck
) -> None:
    world = null_world
    with world.transaction() as tx:
        assert world.place("box", 0, 0) is None
        before = world.digest()
        assert world.place("c", 1, 1).stage == "overlap"
        assert world.place("t1", 8, 0).stage == "region"
        assert world.place("t1", 5, 5, rot=90) is None
        assert world.digest() != before
        tx.commit()
    with world.transaction():
        world.withdraw("box")
        assert world.place("box", 6, 0, rot=90).stage == "legal"
    assert "overlap" in state_check.report()
    assert "cell:c" not in world.kernel.holders_on("ground")


def test_port_shut_both_ways(null_world: World, state_check: StateCheck) -> None:
    world = null_world
    with world.transaction() as tx:
        assert world.place("t1", 2, 2) is None
        assert world.attach_cell("t1", "y") == (3, 2)
        refusal = world.place("c", 3, 2)
        assert refusal.stage == "port_shut"
        assert "t1.y" in refusal.detail
        assert world.place("s1", 5, 2) is None
        assert world.attach_cell("s1", "a") == (4, 2)
        assert world.place("box", 3, 1).stage == "port_shut"
        tx.commit()
    with world.transaction():
        world.withdraw("t1")
        assert world.place("c", 3, 2) is None


def test_port_shut_refuses_a_cell_on_a_held_attach_cell(
    null_world: World, state_check: StateCheck
) -> None:
    world = null_world
    with world.transaction():
        assert world.place("c", 3, 2) is None
        refusal = world.place("t1", 2, 2)
        assert refusal.stage == "port_shut"
        assert "cell:c" in refusal.detail


def test_route_without_a_router_refuses_at_route(
    null_world: World, state_check: StateCheck
) -> None:
    world = null_world
    with world.transaction():
        world.place("t1", 0, 0)
        world.place("s1", 4, 0)
        assert [n.id for n in world.ready_nets("s1")] == ["n1"]
        refusal = world.route("n1")
        assert refusal.stage == "route"
        assert [n.id for n in world.unrouted()] == ["n1"]


class StraightRouter:
    """A router for tests: a straight run from the source's attach cell to the sink's."""

    def route(self, world: World, net_id: str) -> object:
        net = world.netlist.nets[net_id]
        (src,), (dst,) = net.sources, net.sinks
        a, b = world.attach_cell(src.cell, src.pin), world.attach_cell(
            dst.cell, dst.pin
        )
        cells = tuple((x, a[1]) for x in range(min(a[0], b[0]), max(a[0], b[0]) + 1))
        layer = world.carrier_layer(net.carrier)
        occupant = Occupant(kind="wire", carrier=net.carrier, id=net_id)
        for xy in cells:
            if world.may_occupy(layer, xy, occupant) is not None:
                return world.physics.diagnose(
                    world,
                    (
                        Refusal(
                            stage="route",
                            subject=f"net:{net_id}",
                            detail=f"{xy} is held",
                        ),
                    ),
                )
        world.set_wire(
            Wire(
                net=net_id,
                segments=(Segment(carrier=net.carrier, layer=layer, cells=cells),),
            )
        )
        return None


def test_place_routes_what_is_ready_and_rips_what_it_covers() -> None:
    problem = null_problem()
    world = World(problem, get(problem.physics), router=StraightRouter())
    check = StateCheck().mount(world)
    with world.transaction() as tx:
        assert world.place("t1", 0, 2) is None
        assert world.place("s1", 5, 2) is None
        assert "n1" in world.wires
        assert world.kernel.holders_at("ground", (3, 2)) == ("wire:n1",)
        before = world.digest()
        assert world.place("c", 3, 2).stage == "route"
        assert world.digest() == before
        assert world.kernel.holders_at("ground", (3, 2)) == ("wire:n1",)
        world.withdraw("s1")
        assert "n1" not in world.wires
        assert world.kernel.free_for("ground", [(2, 2), (3, 2)])
        tx.commit()
    assert "route n1 -> ok" in check.report()


def test_reservations_block_other_carriers(
    null_world: World, state_check: StateCheck
) -> None:
    world = null_world
    with world.transaction() as tx:
        world.reserve("ch", "ground", [(0, 5), (1, 5), (2, 5)], carrier="wire")
        assert world.place("c", 1, 5).stage == "overlap"
        world.release("ch")
        assert world.place("c", 1, 5) is None
        tx.commit()
    assert world.reservations == {}


def test_snapshot_restore_and_frozen_forms(
    null_world: World, state_check: StateCheck
) -> None:
    world = null_world
    kernel = world.kernel
    with world.transaction() as tx:
        world.place("box", 0, 0)
        world.place("t1", 4, 4)
        tx.commit()
    token = world.snapshot()
    with world.transaction() as tx:
        world.withdraw("box")
        world.place("c", 7, 7)
        tx.commit()
    assert world.digest() != token.digest
    world.restore(token)
    assert world.digest() == token.digest
    assert world.kernel is kernel
    layout = world.freeze()
    assert layout.check_against(world.netlist, world.fabric) == []
    assert layout.problem == world.problem.digest()
    other = World(world.problem, get(world.problem.physics))
    other.load(layout)
    assert other.digest() == world.digest()
    assert other.kernel.holders_at("ground", (1, 1)) == ("cell:box",)


def test_first_open_and_extent(null_world: World, state_check: StateCheck) -> None:
    world = null_world
    with world.transaction() as tx:
        anchor = world.first_open("box")
        assert (anchor.x, anchor.y, anchor.rot) == (0, 0, 0)
        world.place("box", 0, 0)
        anchor = world.first_open("box")
        assert (anchor.x, anchor.y) == (2, 0)
        world.place("c", 7, 7)
        tx.commit()
    assert world.extent() == (0, 0, 8, 8)
    assert world.free_for("BOX", 6, 6, 0) is False
    assert world.free_for("BOX", 2, 2, 0) is True
    assert world.occupancy("ground").sum() == 5


def test_in_order_walk_completes_the_null_problem() -> None:
    problem = null_problem(width=12, height=12, taps=3)
    world = World(problem, get(problem.physics))
    check = StateCheck().mount(world)
    order, _ = world.netlist.flow_order()
    with world.transaction() as tx:
        for cell_id in order:
            anchor = world.first_open(cell_id)
            assert anchor is not None, cell_id
            assert world.place(cell_id, anchor.x, anchor.y, anchor.rot) is None, cell_id
        tx.commit()
    assert set(world.placements) == set(world.netlist.cells)
    assert check.failures == []
    assert world.freeze().check_against(world.netlist, world.fabric) == []


class PoweredNull(NullPhysics):
    """The null pack with one field: every CELL needs power from a 1x1 emitter of radius 1."""

    id = "powered-null"

    def __init__(self) -> None:
        super().__init__()
        self.fields = GreedyCover(
            (
                Emitter(
                    kind="power",
                    footprint=LIBRARY["CELL"].model_copy(update={"id": "PYLON"}),
                    reach=Reach(radius=1),
                ),
            )
        )
        self.fields.needs = lambda cell: ("power",) if cell.footprint == "CELL" else ()


def test_place_covers_needs_with_units() -> None:
    problem = null_problem(width=6, height=6)
    world = World(problem, PoweredNull())
    check = StateCheck().mount(world)
    with world.transaction() as tx:
        assert world.place("c", 2, 2) is None
        assert len(world.units) == 1
        unit = next(iter(world.units.values()))
        assert unit.owner == "field:power"
        assert (2, 2) in world.field_coverage("power")
        assert (
            world.place_unit(
                UnitPlacement(
                    kind="power",
                    footprint=world.library["PYLON"],
                    x=unit.x,
                    y=unit.y,
                    owner="x",
                )
            ).stage
            == "overlap"
        )
        tx.commit()
    with world.transaction():
        world.withdraw("c")
        assert len(world.units) == 1
    assert check.failures == []


def test_place_instance_uses_the_macro_fragment(kl_fixtures) -> None:
    netlist = Netlist.parse((kl_fixtures / "half_adder_hier.kl").read_text())
    physics = get("null")
    fabric = physics.fabric({"width": 24, "height": 24})
    problem = Problem(physics=physics.ref, fabric=fabric, netlist=netlist, params={})
    world = World(problem, physics)
    instances = [c for c in netlist.cells.values() if c.macro]
    if not instances:
        pytest.skip("fixture has no macro instances")
    with world.transaction() as tx:
        assert world.place_instance(instances[0].id, 2, 2) is None
        tx.commit()
    assert all(owner == instances[0].id for owner in world.membership.values())
    frozen = world.freeze(hierarchical=True)
    assert instances[0].id in frozen.instances
    assert frozen.flatten(netlist).placements == world.freeze().placements


def test_python_kernel_round_trips_bytes() -> None:
    kernel = PyKernel(4, 4, ("ground", "overhead"))
    kernel.occupy("ground", [(0, 0), (1, 0)], "cell:a")
    kernel.occupy("ground", [(1, 0)], "wire:n")
    kernel.occupy("overhead", [(3, 3)], "unit:u")
    blob = kernel.save()
    assert kernel.holders_at("ground", (1, 0)) == ("cell:a", "wire:n")
    assert kernel.extent() == (0, 0, 4, 4)
    assert kernel.extent("ground") == (0, 0, 2, 1)
    kernel.free("ground", [(1, 0)], "cell:a")
    assert kernel.cells_of("cell:a") == {"ground": frozenset({(0, 0)})}
    kernel.load(blob)
    assert kernel.save() == blob
    assert kernel.holders_on("ground") == ("cell:a", "wire:n")
    assert kernel.integral("ground")[-1, -1] == 2
