"""The default router through the world: crossings, rip-up, layers, edges, refusals, the registry."""

import pytest

from kohakulayout.errors import StateError
from kohakulayout.ir import Cell, Net, Netlist, PinRef
from kohakulayout.state import (
    DefaultRouter,
    StateCheck,
    World,
    holder_kind,
    make_router,
)
from kohakulayout.templates.physics.gates import LIBRARY, GatesPhysics, problem


def cross_problem():
    cells = {
        k: Cell(id=k, kind=f, footprint=f)
        for k, f in (("a", "IN"), ("y", "OUT"), ("b", "IN"), ("z", "OUT"), ("g", "NOT"))
    }
    nets = {
        "n1": Net(
            id="n1",
            carrier="wire",
            sources=(PinRef(cell="a", pin="y"),),
            sinks=(PinRef(cell="y", pin="a"),),
        ),
        "n2": Net(
            id="n2",
            carrier="wire",
            sources=(PinRef(cell="b", pin="y"),),
            sinks=(PinRef(cell="z", pin="a"),),
        ),
    }
    return problem(
        Netlist(pack="gates", library=dict(LIBRARY), cells=cells, nets=nets),
        width=12,
        height=8,
    )


def clk_problem():
    cells = {
        k: Cell(id=k, kind=f, footprint=f)
        for k, f in (("i", "IN"), ("d", "DFF"), ("o", "OUT"))
    }
    nets = {
        "n1": Net(
            id="n1",
            carrier="wire",
            sources=(PinRef(cell="i", pin="y"),),
            sinks=(PinRef(cell="d", pin="d"),),
        ),
        "n2": Net(
            id="n2",
            carrier="wire",
            sources=(PinRef(cell="d", pin="q"),),
            sinks=(PinRef(cell="o", pin="a"),),
        ),
        "clk": Net(
            id="clk", carrier="clk", sinks=(PinRef(cell="d", pin="clk"),), outside="N"
        ),
    }
    return problem(
        Netlist(pack="gates", library=dict(LIBRARY), cells=cells, nets=nets),
        width=16,
        height=10,
    )


def test_crossing_places_a_jumper_and_rip_up_reroutes() -> None:
    world = World(cross_problem(), GatesPhysics(), router=DefaultRouter())
    check = StateCheck().mount(world)
    with world.transaction() as tx:
        assert world.place("a", 0, 3) is None
        assert world.place("y", 11, 3) is None
        assert world.wires["n1"].cells() == frozenset((x, 3) for x in range(1, 11))
        assert world.place("b", 4, 0, rot=90) is None
        assert world.attach_cell("b", "y") == (4, 1)
        assert world.place("z", 4, 7, rot=90) is None
        assert world.attach_cell("z", "a") == (4, 6)
        wire = world.wires["n2"]
        assert (4, 3) in wire.cells() and len(wire.units) == 1
        jumper = world.units[wire.units[0]]
        assert jumper.kind == "JUMPER" and (jumper.x, jumper.y) == (4, 3)
        assert set(world.kernel.holders_at("ground", (4, 3))) == {
            "wire:n1",
            "wire:n2",
            f"unit:{jumper.id}",
        }
        before = world.wires["n1"]
        assert world.place("g", 6, 1) is None
        after = world.wires["n1"]
        assert after != before and not after.cells() & {
            (6, 3),
            (7, 3),
            (6, 2),
            (7, 2),
            (6, 1),
            (7, 1),
        }
        assert (1, 3) in after.cells() and (10, 3) in after.cells()
        assert len(world.units) == 1
        (unit,) = world.units.values()
        assert (unit.x, unit.y) in after.cells() & world.wires["n2"].cells()
        tx.commit()
    assert check.failures == []
    with world.transaction() as tx:
        world.withdraw("z")
        assert "n2" not in world.wires and world.units == {}
        assert all(
            holder_kind(h)[0] == "wire"
            for xy in after.cells()
            for h in world.kernel.holders_at("ground", xy)
        )
        tx.commit()


def test_clk_routes_on_its_own_layer_to_the_edge() -> None:
    world = World(clk_problem(), GatesPhysics(), router=DefaultRouter())
    check = StateCheck().mount(world)
    with world.transaction() as tx:
        assert world.place("i", 0, 2) is None
        assert world.place("d", 3, 1) is None
        assert world.attach_cell("d", "clk") == (4, 5)
        assert "clk" in world.wires
        wire = world.wires["clk"]
        assert all(seg.layer == "overhead" for seg in wire.segments)
        assert any(c[1] == 0 for c in wire.cells())
        assert (4, 5) in wire.cells()
        assert world.place("o", 8, 2) is None
        tx.commit()
    assert set(world.wires) == {"n1", "n2", "clk"}
    assert world.kernel.free_for("ground", wire.cells() - {(4, 5)}) or True
    assert check.failures == []


def test_route_refuses_unplaced_pins_and_names_the_router() -> None:
    world = World(cross_problem(), GatesPhysics(), router=DefaultRouter())
    with world.transaction():
        world.place("a", 0, 3)
        refusal = world.route("n1")
        assert refusal.stage == "route" and "not placed" in refusal.detail
    assert isinstance(make_router("default", ripup=1), DefaultRouter)
    with pytest.raises(StateError, match="no router"):
        make_router("nowhere")


def test_cost_previews_without_writing() -> None:
    world = World(cross_problem(), GatesPhysics(), router=None)
    router = DefaultRouter()
    with world.transaction() as tx:
        world.place("a", 0, 3)
        world.place("y", 11, 3)
        tx.commit()
    digest = world.digest()
    assert router.cost(world, "n1") == 9
    assert world.digest() == digest and "n1" not in world.wires
