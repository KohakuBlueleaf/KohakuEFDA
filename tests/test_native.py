"""The native routing grid against the Python one it mirrors.

A mirror that is only ever read through itself cannot be witnessed, so every case here runs the
same instance through both and compares: the occupancy the two hold, and the path each search
returns. Skipped when the extension has not been built (``maturin develop --release``, or
``cargo build --release`` and the library copied to ``src/kohakuefda/_native.pyd``).
"""

import random
from pathlib import Path

import pytest

from kohakuefda.layout.pipeline import layout_scenario
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.geometry import Edge
from kohakuefda.model.scenario import Scenario
from kohakuefda.route import pathfinder
from kohakuefda.route.pathfinder import (
    AXIS_CODE,
    NATIVE,
    RouteGrid,
    astar,
    search,
)

pytestmark = pytest.mark.skipif(not NATIVE, reason="the native module is not built")
GROUND = 0
SKY = 1


def _grid(width: int = 24, height: int = 24) -> RouteGrid:
    return RouteGrid(width, height, [set(), set()], 0.5, 4.0, 1.0)


def _mirrors(grid: RouteGrid) -> None:
    """The native grid holds exactly what the Python one does."""
    for layer in (GROUND, SKY):
        assert {tuple(c) for c in grid.native.blocked(layer)} == grid.blocked[layer]
        assert {tuple(c) for c in grid.native.units(layer)} == grid.units[layer]
        native = {
            ((x, y), wire, axis) for x, y, wire, axis in grid.native.holders(layer)
        }
        python = {
            (cell, grid._code(wire), AXIS_CODE[axis])
            for cell, holders in grid.holders[layer].items()
            for wire, axis in holders.items()
        }
        assert native == python


def test_the_mirror_follows_every_kind_of_change() -> None:
    grid = _grid()
    grid.block(GROUND, (3, 3))
    grid.block(SKY, (4, 4))
    grid.add_unit(GROUND, (5, 5))
    grid.add_wire(GROUND, "w0", [(1, 1), (2, 1), (3, 1)], (0, 1), (4, 1))
    grid.add_wire(SKY, "w1", [(1, 2), (2, 2)], (0, 2), (3, 2))
    grid.reserve(GROUND, (7, 7), "w0")
    _mirrors(grid)

    grid.unblock(GROUND, (3, 3))
    grid.discard_unit(GROUND, (5, 5))
    grid.remove_wire(GROUND, "w0", [(1, 1), (2, 1), (3, 1)])
    grid.unreserve(GROUND, (7, 7), "w0")
    _mirrors(grid)


def test_a_pushed_layer_replaces_what_the_mirror_held() -> None:
    grid = _grid()
    grid.add_wire(GROUND, "w0", [(1, 1), (2, 1)], (0, 1), (3, 1))
    grid.blocked[GROUND] = {(9, 9), (9, 10)}
    grid.units[GROUND] = {(8, 8)}
    grid.holders[GROUND] = {(5, 5): {"w3": "v"}}
    grid.reserved[GROUND] = {(6, 6): {"w3"}}
    grid.push(GROUND)
    _mirrors(grid)


def _instance(seed: int) -> tuple[RouteGrid, dict, dict, int, str]:
    """A grid with machines, lanes, units and reservations scattered over it."""
    rng = random.Random(seed)
    grid = _grid()
    for _ in range(rng.randint(10, 60)):
        cell = (rng.randrange(24), rng.randrange(24))
        grid.block(rng.choice((GROUND, SKY)), cell)
    for index in range(rng.randint(1, 8)):
        x = rng.randrange(24)
        y0 = rng.randrange(20)
        cells = [(x, y) for y in range(y0, min(24, y0 + rng.randint(2, 6)))]
        layer = rng.choice((GROUND, SKY))
        grid.add_wire(layer, f"w{index}", cells, (x, y0 - 1), (x, y0 + len(cells)))
    for _ in range(rng.randint(0, 5)):
        grid.add_unit(rng.choice((GROUND, SKY)), (rng.randrange(24), rng.randrange(24)))
    for _ in range(rng.randint(0, 5)):
        grid.reserve(GROUND, (rng.randrange(24), rng.randrange(24)), "w0")
    starts = {(rng.randrange(24), rng.randrange(24)): None}
    goals = {(rng.randrange(24), rng.randrange(24)): None}
    if rng.random() < 0.3:
        starts[(rng.randrange(24), rng.randrange(24))] = {Edge.N, Edge.E}
    if rng.random() < 0.3:
        goals[(rng.randrange(24), rng.randrange(24))] = {Edge.S, Edge.W}
    return grid, starts, goals, rng.choice((GROUND, SKY)), "w9"


@pytest.mark.parametrize("seed", range(60))
def test_the_native_search_finds_the_path_the_python_one_finds(seed: int) -> None:
    grid, starts, goals, layer, wire = _instance(seed)
    for share in (True, False):
        for limit in (40.0, float("inf")):
            mine = astar(grid, layer, wire, starts, goals, 2.0, share, limit)
            oracle = search(grid, layer, wire, starts, goals, 2.0, share, limit)
            assert mine == oracle, (seed, share, limit)


@pytest.mark.parametrize("seed", range(20))
def test_the_two_agree_on_tree_cells_a_wire_may_attach_to(seed: int) -> None:
    grid, starts, goals, layer, wire = _instance(seed + 500)
    shared = set(list(goals)[:1])
    mine = astar(grid, layer, wire, starts, goals, 2.0, False, float("inf"), shared)
    oracle = search(grid, layer, wire, starts, goals, 2.0, False, float("inf"), shared)
    assert mine == oracle


@pytest.fixture(scope="module")
def dataset() -> Dataset:
    root = Path(__file__).resolve().parents[1]
    return Dataset.load(root / "data" / "1.5.3@9764758-3" / "dataset.json")


def test_a_layout_run_routes_the_same_either_way(dataset: Dataset) -> None:
    """The whole engine, once with the native grid and once without: the same layout."""
    root = Path(__file__).resolve().parents[1]
    scenario = Scenario.from_toml(
        root / "tests" / "fixtures" / "scenario_gas_xiranite.toml"
    )
    params = {"seed": 3, "frame_every": 100000, "workers": 1}
    with_native = layout_scenario(dataset, scenario, params).layout
    grid_class = pathfinder._Grid
    pathfinder._Grid = None
    try:
        without = layout_scenario(dataset, scenario, params).layout
    finally:
        pathfinder._Grid = grid_class
    assert with_native.model_dump() == without.model_dump()
