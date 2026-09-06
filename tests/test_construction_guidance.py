"""Construction proposal lookahead, scored partial states and in-area measurement."""

import json
from itertools import pairwise
from pathlib import Path

import numpy as np
import pytest

from kohakuefda.framework import problem_of
from kohakuefda.framework.assessment import metrics_of
from kohakuefda.framework.control import LocalBudgetExhausted
from kohakuefda.framework.runtime import Runner
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.layout import Layout, Segment
from kohakuefda.model.scenario import Scenario
from kohakuefda.plan.netlist import build_netlist
from kohakuefda.plan.planner import plan
from kohakuefda.route.pathfinder import NATIVE
from kohakuefda.solvers.local import DEFAULTS, HillClimbing, SimulatedAnnealing
from kohakuefda.solvers.local.frontier import Frontier, endpoint_distances, window_sum
from kohakuefda.solvers.local.moves import ConstructionMoves
from kohakuefda.solvers.regional import DEFAULTS as REGIONAL_DEFAULTS

ROOT = Path(__file__).resolve().parents[1]
BACKENDS = ["python"] + (["native"] if NATIVE else [])


@pytest.fixture(scope="module")
def dataset():
    return Dataset.load(ROOT / "data/1.5.3@9764758-3/dataset.json")


def problem_for(dataset, name):
    scenario = Scenario.from_toml(ROOT / f"tests/fixtures/scenario_{name}.toml")
    planned = plan(dataset, scenario)
    return problem_of(dataset, build_netlist(dataset, scenario, planned), planned)


def test_recorded_wuling50_problem_preserves_the_players_board(dataset):
    problem = problem_for(dataset, "wuling_battery50")
    ctx = Runner(problem, settings={"check_rates": False}).context
    x0, y0, x1, y1 = ctx.area
    assert (x1 - x0, y1 - y0) == (50, 50)
    assert len(ctx.blocks) == 70
    assert json.loads(problem.netlist_json)["scenario"]["targets"] == {
        "item_proc_battery_5": "min"
    }


def test_endpoint_transform_matches_explicit_nearest_endpoint_distances():
    rng = np.random.default_rng(4)
    yy, xx = np.indices((29, 41))
    for count in (1, 7, 300):
        cells = tuple(
            (int(x), int(y))
            for x, y in zip(rng.integers(0, 41, count), rng.integers(0, 29, count))
        )
        expected = np.minimum.reduce([abs(xx - x) + abs(yy - y) for x, y in cells])
        np.testing.assert_array_equal(endpoint_distances((41, 29), cells), expected)
    assert np.all(endpoint_distances((41, 29), ()) == 70)


def test_window_obstruction_matches_every_rectangle():
    mask = np.random.default_rng(7).integers(0, 2, (17, 19))
    for width, height in ((1, 1), (3, 5), (7, 7), (19, 17)):
        found = window_sum(mask, width, height)
        expected = [
            [mask[y : y + height, x : x + width].sum() for x in range(20 - width)]
            for y in range(18 - height)
        ]
        np.testing.assert_array_equal(found, expected)


@pytest.mark.parametrize("backend", BACKENDS)
def test_lookahead_budget_failure_rolls_back_the_whole_build_trial(dataset, backend):
    ctx = Runner(
        problem_for(dataset, "basic"),
        settings={"backend": backend, "check_rates": False},
    ).context
    builder = ctx.builder()
    moves = ConstructionMoves(ctx, DEFAULTS)
    block_id = next(i for i, b in ctx.blocks.items() if b.kind == "depot")
    moves.repair.proposals.reset(0)
    anchors = moves.repair.proposals.ranked(block_id, 0, moves.repair.rng)
    before = builder.diagnostic()
    with (
        pytest.raises(LocalBudgetExhausted),
        builder.transaction(),
        ctx.budget.limit(actions=2),
    ):
        moves.repair.insert(block_id, anchors)
    assert builder.diagnostic() == before
    assert not ctx.view.unrouted


@pytest.mark.parametrize("solver", [HillClimbing, SimulatedAnnealing])
def test_guided_construction_has_a_nonflat_equal_count_gradient(dataset, solver):
    problem = problem_for(dataset, "dense_valley12")
    events = []
    options = {
        "construction_steps": 20,
        "improvement_steps": 0,
        "candidates": 10,
        "frontier_weight": 0.5,
        "local_repair_every": 4,
        "insertion_lookahead": 2,
        "construction_temperature": 20,
        "construction_final_temperature": 20,
    }
    result = Runner(
        problem,
        settings={"backend": BACKENDS[-1], "check_rates": False},
        observe=events.append,
    ).run(solver(**options))
    rows = [json.loads(e.payload_json) for e in events if e.kind == "transition"]
    equal = [
        r
        for r in rows
        if r["candidate_missing"] == r["parent_missing"]
        and r["outcome"] not in ("duplicate", "interrupted")
    ]
    assert equal and any(r["delta"] != 0 for r in equal)
    for row in equal:
        assert row["delta"] == pytest.approx(
            0.5 * (row["candidate_potential"] - row["parent_potential"])
        )
    if solver is HillClimbing:
        assert all(r["delta"] <= 0 for r in rows if r["accepted"])
        assert all(
            r["candidate_potential"] <= r["parent_potential"]
            for r in equal
            if r["accepted"]
        )
    assert all(a["next_parent"] == b["parent"] for a, b in pairwise(rows))
    assert not result.best_routed


@pytest.mark.parametrize("backend", BACKENDS)
def test_external_pipe_detours_do_not_inflate_live_or_materialized_area(
    dataset, backend
):
    runner = Runner(
        problem_for(dataset, "basic"),
        settings={"backend": backend, "check_rates": False},
    )
    site = runner.backend.site
    x0, y0, _, _ = site.area
    wire = next(w for w in site.wires if w.kind == "pipe")
    inside = [(x0 + 3, y) for y in range(y0, y0 + 4)]
    found = []
    for start in (x0 - 1, x0 - 5):
        cells = [(x, y0 - 1) for x in range(start, x0 + 4)] + inside
        if wire.cells:
            site.grid.remove_wire(1, wire.id, wire.cells)
        wire.cells = cells
        site.grid.add_wire(1, wire.id, cells, (start - 1, y0 - 1), (x0 + 3, y0 + 4))
        layout = Layout(
            dataset_version=dataset.version.id,
            basement=site.netlist.scenario.basement,
            width=site.width,
            height=site.height,
            area=site.area,
            segments=[Segment(id=wire.id, kind="pipe", cells=cells)],
        )
        found.append(metrics_of(site, layout, []))
        assert site.bbox() == (x0 + 3, y0, x0 + 4, y0 + 4)
        assert set(cells) <= site.occupied()
        assert tuple(runner.backend.frame("build")["rect"]) == site.bbox()
    for key in ("area", "width", "height", "waste", "occupied_cells"):
        assert found[0][key] == found[1][key]
    assert found[0]["area"] == 4
    assert found[1]["length"] > found[0]["length"]


def test_frontier_complete_state_has_no_missing_potential(dataset):
    runner = Runner(
        problem_for(dataset, "valley_battery"), settings={"check_rates": False}
    )
    result = runner.run(HillClimbing(improvement_steps=0))
    assert result.current.assessment.routed
    assert Frontier(runner.context, REGIONAL_DEFAULTS).potential() == 0
