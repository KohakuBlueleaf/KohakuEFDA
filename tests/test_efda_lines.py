"""The lines representation: one group per chain with its bricks, rows by depth from the bus, loops in one row turned about, bricks over the machines they feed, side cells beside their machine, every box held until placed, the groups packed against the bus."""

import random
from itertools import combinations, pairwise
from pathlib import Path

from kohakuefda.layout.settings import framework_id, router_of
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.scenario import Scenario
from kohakuefda.physics.boundaries import BRICK_KINDS, PART_KIND, area_rect
from kohakuefda.plan.netlist import build_netlist
from kohakuefda.plan.planner import plan
from kohakuefda.solvers.lines import EndfieldLines, EndfieldLinesPlan
from kohakuefda.solvers.lines_graph import LineGraph
from kohakuefda.synth import problem_of
from kohakulayout.engine import Budget, Context
from kohakulayout.solvers import known

ROOT = Path(__file__).resolve().parent.parent


def wuling6():
    dataset = Dataset.load(ROOT / "data" / "1.5.3@9764758-3" / "dataset.json")
    scenario = Scenario.from_toml(
        ROOT / "tests" / "fixtures" / "scenario_dense_wuling6.toml"
    )
    netlist = build_netlist(dataset, scenario, plan(dataset, scenario))
    problem = problem_of(dataset, netlist)
    return Context(problem, router=router_of(), budget=Budget(units=10))


def test_the_lines_solver_is_the_studios_lines() -> None:
    assert framework_id("lines") == EndfieldLinesPlan.id == "endfield.lines"
    assert "endfield.lines" in known()


def test_rows_run_by_depth_from_the_bus_with_loops_in_one_row() -> None:
    ctx = wuling6()
    graph = LineGraph(ctx.world)
    depth, groups, rot = graph.depths()
    cells = ctx.world.problem.netlist.cells
    assert all(depth[b] == 0 for b in graph.bricks)
    assert sorted(c for g in groups for c in g) == sorted(graph.items)
    group_of = {c: g for g, group in enumerate(groups) for c in group}
    for brick in graph.bricks:
        assert group_of[brick] == group_of[graph.links[brick][0][0]]
    fed = [any(b in g for b in graph.bricks) for g in groups]
    assert fed[0] and fed == sorted(fed, reverse=True)
    assert len(groups) > 2 and not fed[-1]
    for item, links in graph.links.items():
        for taker, _, _, carrier, _ in links:
            if carrier == "pipe" or group_of[item] != group_of[taker]:
                continue
            if rot.get(item, 0) == 0 and rot.get(taker, 0) == 0:
                assert depth[taker] >= depth[item] or graph.loop_of(
                    item
                ) is graph.loop_of(taker)
    loops = [loop for loop in graph.regions()[1] if len(loop) > 1]
    assert loops
    for loop in loops:
        assert len({depth[c] for c in loop}) == 1
        assert {rot.get(c, 0) for c in loop} == {0, 180}
    for side, mate in graph.side_of.items():
        assert cells[side].kind in ("outlet", "inlet") and mate in graph.machines


def test_the_structure_lays_bricks_in_one_run_over_the_machines_they_feed() -> None:
    ctx = wuling6()
    rep = EndfieldLines()
    structure = rep.initial(ctx, random.Random(0))
    graph = rep.graph(ctx.world)
    boxes, frames, parts = rep.frames(structure, ctx)
    x0, y0, x1, y1 = area_rect(ctx.world.fabric)
    placed = [c for row in structure["rows"] for c in row]
    assert sorted(placed) == sorted(c for c in boxes if c not in graph.parts)
    assert all(
        x0 <= x and x + w <= x1 and y0 <= y and y + h <= y1
        for x, y, w, h in boxes.values()
    )
    run = sorted((boxes[b][0], boxes[b][0] + boxes[b][2]) for b in graph.bricks)
    assert all(b <= c for (_, b), (c, _) in pairwise(run))
    bus = sorted((x, x + boxes[p][2]) for p, x, _, _ in parts)
    assert bus[0][0] <= run[0][0] + 1 and run[-1][1] - 1 <= bus[-1][1]
    for a, b in combinations(range(len(frames)), 2):
        cells_a = {
            (x, y)
            for i in (i for row in frames[a][4] for i in row)
            for x in range(boxes[i][0], boxes[i][0] + boxes[i][2])
            for y in range(boxes[i][1], boxes[i][1] + boxes[i][3])
        }
        cells_b = {
            (x, y)
            for i in (i for row in frames[b][4] for i in row)
            for x in range(boxes[i][0], boxes[i][0] + boxes[i][2])
            for y in range(boxes[i][1], boxes[i][1] + boxes[i][3])
        }
        assert cells_a.isdisjoint(cells_b)
    assert all(b == c for (_, b), (c, _) in pairwise(bus))
    kinds = ctx.world.problem.netlist.cells
    assert all(kinds[p].kind == PART_KIND for p, *_ in parts)
    for brick in graph.bricks:
        assert kinds[brick].kind in BRICK_KINDS
        taker = graph.links[brick][0][0]
        assert boxes[brick][1] + boxes[brick][3] + 1 == boxes[taker][1]
        assert (
            boxes[taker][0] - 1
            <= boxes[brick][0] + 1
            <= boxes[taker][0] + boxes[taker][2]
        )
    for rows in structure["groups"]:
        for row in rows:
            edges = sorted((boxes[i][0], boxes[i][0] + boxes[i][2]) for i in row)
            assert all(b <= c for (_, b), (c, _) in pairwise(edges))
    for side, mate in graph.side_of.items():
        sx, sy, sw, _ = boxes[side]
        mx, my, mw, _ = boxes[mate]
        assert sx + sw < mx or sx > mx + mw
        assert sy >= my
    holds = rep.holds(structure, ctx)
    for item, (x, y, w, h) in boxes.items():
        if item in graph.parts:
            continue
        held = {c for _, cells in holds[item] for c in cells}
        assert {(x + dx, y + dy) for dx in range(w) for dy in range(h)} <= held
    lanes = rep.channels(structure, ctx)
    assert lanes and {carrier for _, _, _, carrier in lanes} == {"belt", "pipe"}
    machine_cells = {
        (x + dx, y + dy)
        for x, y, w, h in boxes.values()
        for dx in range(w)
        for dy in range(h)
    }
    assert not any(c in machine_cells for _, _, cells, _ in lanes for c in cells)
