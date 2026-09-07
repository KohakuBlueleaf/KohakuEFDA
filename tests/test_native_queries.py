"""Batched native queries preserve Python ordering, geometry and retained snapshots."""

import random
from pathlib import Path

import pytest

from kohakuefda.framework import problem_of
from kohakuefda.framework.runtime import Runner
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.geometry import Edge
from kohakuefda.model.scenario import Scenario
from kohakuefda.plan.netlist import build_netlist
from kohakuefda.plan.planner import plan
from kohakuefda.route.pathfinder import NATIVE, RouteGrid
from kohakuefda.solvers.local import HillClimbing, SimulatedAnnealing

ROOT = Path(__file__).resolve().parents[1]
BACKENDS = [False, True] if NATIVE else [False]


def copied_state(grid):
    return (
        [{c: dict(v) for c, v in layer.items()} for layer in grid.holders],
        [{c: set(v) for c, v in layer.items()} for layer in grid.reserved],
        [set(layer) for layer in grid.blocked],
        [set(layer) for layer in grid.owned],
        [set(layer) for layer in grid.units],
        [dict(layer) for layer in grid.history],
        dict(grid._wires),
        dict(grid._names),
    )


@pytest.mark.parametrize("native", BACKENDS)
def test_copy_on_write_nested_marks_survive_repeated_edits_and_restores(native):
    grid = RouteGrid(20, 20, [set(), set()], native=native)
    grid.add_wire(0, "a", [(x, 3) for x in range(2, 12)], (1, 3), (12, 3))
    grid.reserve(0, (3, 3), "a")
    grid.reserve(0, (3, 3), "b")
    grid.block_cells([(6, 6), (6, 7)], True, True)
    outer = (grid.python_state(), grid.save(), copied_state(grid))
    grid.add_wire(0, "b", [(3, y) for y in range(2, 12)], (3, 1), (3, 12))
    inner = (grid.python_state(), grid.save(), copied_state(grid))
    for snapshot in (outer, inner, outer, inner):
        grid.remove_wire(0, "a", [(x, 3) for x in range(2, 12)])
        grid.unreserve(0, (3, 3), "a")
        grid.block_cells([(6, 6), (6, 7)], False)
        grid.add_unit(1, (8, 8))
        grid.charge(0, (9, 9), 9.0)
        grid.restore_python(snapshot[0])
        grid.load(snapshot[1])
        assert copied_state(grid) == snapshot[2]
        grid.holders_at(0, (3, 3)).clear()
        assert copied_state(grid) == snapshot[2]
    assert outer[0][0][0][(4, 3)] is inner[0][0][0][(4, 3)]
    assert outer[0][0][0][(3, 3)] is not inner[0][0][0][(3, 3)]
    with pytest.raises(TypeError):
        outer[0][0][0][(4, 3)]["x"] = "h"
    assert isinstance(outer[0][4][0][(3, 3)], frozenset)


@pytest.mark.parametrize("native", BACKENDS)
def test_batched_footprint_matches_scalar_mirror(native):
    scalar = RouteGrid(20, 20, [set(), set()], native=native)
    batch = RouteGrid(20, 20, [set(), set()], native=native)
    cells = [(x, y) for x in range(4, 10) for y in range(2, 9)]
    for value, owned in ((True, True), (True, False), (False, False), (True, False)):
        batch.block_cells(cells, value, owned)
        for layer in (0, 1):
            for c in cells:
                if value:
                    scalar.block(layer, c, owned)
                else:
                    scalar.unblock(layer, c)
        assert copied_state(batch) == copied_state(scalar)
        for layer in (0, 1):
            assert all(
                batch.is_blocked(layer, c) == scalar.is_blocked(layer, c) for c in cells
            )
        assert batch.extent_in((0, 0, 20, 20)) == scalar.extent_in((0, 0, 20, 20))


@pytest.mark.skipif(not NATIVE, reason="native extension not installed")
@pytest.mark.parametrize("seed", range(6))
def test_native_junction_queries_match_reference_order_through_restore(seed):
    rng = random.Random(seed)
    grids = [RouteGrid(30, 24, [set(), set()], native=n) for n in (False, True)]
    assert hasattr(grids[1].native, "straight_cells")
    chains = []
    for index in range(14):
        y = rng.randrange(1, 23)
        x = rng.randrange(1, 17)
        chain = [(x + k, y) for k in range(12)]
        if index % 2:
            chain.reverse()
        chains.append(chain)
        for grid in grids:
            grid.add_wire(index % 2, str(index), chain[1:-1], chain[0], chain[-1])
    chains += [chains[0], list(reversed(chains[0]))]
    for grid in grids:
        grid.add_unit(1, chains[1][4])
        grid.block_cells([chains[3][5]], True, True)
    states = [(g.python_state(), g.save()) for g in grids]
    for cycle in range(3):
        if cycle:
            for grid, state in zip(grids, states):
                grid.restore_python(state[0])
                grid.load(state[1])
                grid.add_unit(cycle % 2, chains[cycle][6])
        for layer in (0, 1):
            for area in (None, (5, 4, 22, 18), (0, 0, 30, 24), (0, 0, 0, 0)):
                expected = grids[0].straight_cells(layer, chains, area)
                assert list(
                    grids[1].straight_cells(layer, chains, area).items()
                ) == list(expected.items())
                for path in chains:
                    assert grids[1].bridges_outside(layer, path, area) == grids[
                        0
                    ].bridges_outside(layer, path, area)
        for area in ((0, 0, 30, 24), (5, 4, 22, 18), (-3, -3, 50, 50), (0, 0, 0, 0)):
            assert grids[1].extent_in(area) == grids[0].extent_in(area)
    with pytest.raises(ValueError):
        grids[1].native.straight_cells(2, chains, (0, 0, 30, 24))
    with pytest.raises(ValueError):
        grids[1].native.bridges_outside(2, [], (0, 0, 30, 24))


@pytest.mark.parametrize("native", BACKENDS)
def test_junction_turns_crossings_and_original_ring_rules(native):
    grid = RouteGrid(14, 14, [set(), set()], native=native)
    chain = [(2, 3), (3, 3), (4, 3), (5, 3), (5, 4), (5, 5)]
    grid.add_wire(1, "pipe", chain[1:-1], chain[0], chain[-1])
    assert list(grid.straight_cells(1, [chain], (0, 0, 14, 14)).items()) == [
        ((3, 3), Edge.E),
        ((4, 3), Edge.E),
        ((5, 4), Edge.S),
    ]
    grid.add_wire(0, "belt", [(4, 3)], (4, 2), (4, 4))
    assert (4, 3) not in grid.straight_cells(1, [chain], None)
    assert grid.bridges_outside(1, [(3, 3)], (4, 4, 12, 12))
    assert not grid.bridges_outside(1, [(1, 1)], (4, 4, 12, 12))
    assert grid.extent_in((4, 4, 12, 12)) == (5, 4, 6, 5)


@pytest.fixture(scope="module")
def problem():
    dataset = Dataset.load(ROOT / "data/1.5.3@9764758-3/dataset.json")
    scenario = Scenario.from_toml(ROOT / "tests/fixtures/scenario_valley_battery.toml")
    planned = plan(dataset, scenario)
    return problem_of(dataset, build_netlist(dataset, scenario, planned), planned)


@pytest.mark.skipif(not NATIVE, reason="native extension not installed")
@pytest.mark.parametrize("solver", [HillClimbing, SimulatedAnnealing])
def test_native_and_fallback_match_routed_trajectory_and_budget(problem, solver):
    results = []
    for backend in ("python", "native"):
        runner = Runner(
            problem,
            settings={"backend": backend, "check_rates": False, "max_actions": 700},
        )
        results.append(runner.run(solver()))
    assert results[0].work == results[1].work
    assert results[0].current.layout_json == results[1].current.layout_json
    assert results[0].best_routed.layout_json == results[1].best_routed.layout_json
