"""The path finder on the null pack: straight runs, detours, walls, corridors, crossings, the step budget."""

from kohakulayout.physics import get
from kohakulayout.state import World
from kohakulayout.state.router import Costs, Search, find
from kohakulayout.state.router.pathfinder import straight_through
from kohakulayout.templates.physics.gates import GatesPhysics
from kohakulayout.templates.physics.null import problem


def search(world: World, net_id: str = "n1", **costs: int) -> Search:
    return Search(
        world=world,
        net_id=net_id,
        carrier="wire",
        layer="ground",
        costs=Costs(**costs),
        walls=frozenset(),
        history={},
    )


def test_straight_run_and_detour() -> None:
    world = World(problem(taps=2), get("null"))
    found = find(search(world), frozenset({(0, 0)}), frozenset({(7, 0)}))
    assert found.cells == tuple((x, 0) for x in range(8)) and found.cost == 7
    with world.transaction() as tx:
        world.place("box", 3, 0)
        tx.commit()
    found = find(search(world), frozenset({(0, 0)}), frozenset({(7, 0)}))
    assert found is not None and found.cost > 7
    assert not any(c in {(3, 0), (4, 0), (3, 1), (4, 1)} for c in found.cells)
    assert found.cells[0] == (0, 0) and found.cells[-1] == (7, 0)


def test_reservations_are_walls_or_corridors() -> None:
    world = World(problem(taps=2), get("null"))
    with world.transaction() as tx:
        world.reserve("wall", "ground", [(x, 0) for x in range(1, 7)], carrier="clk")
        tx.commit()
    found = find(search(world), frozenset({(0, 0)}), frozenset({(7, 0)}))
    assert found is not None and all(c[1] > 0 or c[0] in (0, 7) for c in found.cells)
    with world.transaction() as tx:
        world.release("wall")
        world.reserve(
            "corridor", "ground", [(x, 0) for x in range(1, 7)], carrier="wire"
        )
        tx.commit()
    found = find(search(world), frozenset({(0, 0)}), frozenset({(7, 0)}))
    assert found.cells == tuple((x, 0) for x in range(8))


def test_step_budget_and_missing_path() -> None:
    world = World(problem(taps=2), get("null"))
    assert (
        find(search(world, max_steps=3), frozenset({(0, 0)}), frozenset({(7, 7)}))
        is None
    )
    with world.transaction() as tx:
        world.reserve("ring", "ground", [(1, 0), (0, 1), (1, 1)], carrier="clk")
        tx.commit()
    assert find(search(world), frozenset({(0, 0)}), frozenset({(7, 7)})) is None


def test_other_wires_block_or_cross() -> None:
    from kohakulayout.ir import Segment, Wire

    world = World(problem(taps=2), get("null"))
    with world.transaction() as tx:
        world.set_wire(
            Wire(
                net="n2",
                segments=(
                    Segment(
                        carrier="wire",
                        layer="ground",
                        cells=tuple((4, y) for y in range(8)),
                    ),
                ),
            )
        )
        tx.commit()
    assert straight_through(world, "ground", "n2", (4, 3), (1, 0))
    assert not straight_through(world, "ground", "n2", (4, 3), (0, 1))
    assert find(search(world), frozenset({(0, 3)}), frozenset({(7, 3)})) is None
    crossing = World(problem(taps=2), GatesPhysics())
    with crossing.transaction() as tx:
        crossing.set_wire(
            Wire(
                net="n2",
                segments=(
                    Segment(
                        carrier="wire",
                        layer="ground",
                        cells=tuple((4, y) for y in range(8)),
                    ),
                ),
            )
        )
        tx.commit()
    found = find(search(crossing), frozenset({(0, 3)}), frozenset({(7, 3)}))
    assert found is not None and found.crossings == (((4, 3), "n2", False),)
    assert found.cells == tuple((x, 3) for x in range(8))
