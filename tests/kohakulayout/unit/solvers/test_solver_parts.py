"""The parts the family shares: anchors, proposals, policy, compaction candidates, parallel slices."""

import random

from kohakulayout.engine import Budget, Context
from kohakulayout.pipeline import solve
from kohakulayout.solvers import ANCHORS, anchors_for
from kohakulayout.solvers.local.compact import cut_candidates, relocate
from kohakulayout.solvers.local.frontier import Frontier, endpoint_distances
from kohakulayout.solvers.local.policy import decide, layout_delta, temperature
from kohakulayout.solvers.regional.candidates import Proposals
from kohakulayout.solvers.regional.search import Search
from kohakulayout.templates.physics.gates import from_expressions, problem


def placed_context() -> Context:
    ctx = Context(
        problem(from_expressions("y = a & b"), width=16, height=8), router="default"
    )
    for cell_id, anchor in (("a", (0, 1)), ("b", (0, 3)), ("g1", (4, 1))):
        assert ctx.attempt(lambda b, c=cell_id, a=anchor: b.place(c, a)).ok
    return ctx


def test_proposals_rank_toward_targets_and_respect_the_pack() -> None:
    ctx = placed_context()
    proposals = Proposals(ctx.world, {"candidates": 5, "gap": 1})
    proposals.reset(1)
    ranked = proposals.ranked("y", 0, random.Random(1))
    assert ranked and all(a.x == 15 for a in ranked)
    assert proposals.offsets("g1", 0) == {"a": (-1, 0), "b": (-1, 2), "y": (3, 1)}
    assert proposals.targets("y") == [("a", [(7, 2)])]
    assert ranked[0].y in (1, 2, 3)
    assert set(ANCHORS) == {"every", "facing", "frontier", "group"}
    facing = list(anchors_for("facing", ctx.world, "y", random.Random(0)))
    assert facing and abs(facing[0].y - 2) <= 1
    near = list(anchors_for("frontier", ctx.world, "y", random.Random(0)))
    assert len(near) == len(list(ctx.world.anchors("y")))


def test_policy_and_cooling() -> None:
    rng = random.Random(0)
    assert (
        decide("climb", -1.0, 0.0, rng).accepted
        and not decide("climb", 1.0, 5.0, rng).accepted
    )
    hot = [decide("anneal", 0.1, 10.0, rng).accepted for _ in range(50)]
    assert any(hot) and not decide("anneal", 1.0, 0.0, rng).accepted
    assert (
        temperature(2.0, 0.5, 0, 100) == 2.0
        and abs(temperature(2.0, 0.5, 100, 100) - 0.5) < 1e-9
    )
    assert temperature(0.0, 0.0, 5, 10) == 0.0
    before = {"area": 100, "wire_cells": 10}
    assert layout_delta(before, {"area": 90, "wire_cells": 40}, 400, 0.5) < 0
    assert 0 < layout_delta(before, {"area": 100, "wire_cells": 40}, 400, 0.5) < 1 / 400


def test_cut_candidates_close_empty_lines_and_relocate_attempts() -> None:
    ctx = placed_context()
    movable = frozenset(
        c
        for c, cell in ctx.world.netlist.cells.items()
        if cell.constraint.kind == "free"
    )
    cuts = cut_candidates(ctx.world, movable)
    assert cuts and all("g1" in moves for _, moves in cuts)
    _, best = cuts[0]
    result = ctx.attempt(lambda b, m=best: relocate(b, m))
    assert result.ok and ctx.world.placements["g1"].x < 4


def test_frontier_potential_is_bounded_and_falls_when_room_appears() -> None:
    ctx = placed_context()
    crowded = Frontier(ctx.world).potential()
    assert 0.0 <= crowded <= 2.0
    table = endpoint_distances(4, 3, ((0, 0),))
    assert table[2, 3] == 5 and table[0, 0] == 0


def test_parallel_spread_slices_complete_the_toy() -> None:
    result = solve(
        problem(from_expressions("y = a & b | ~c"), width=24, height=12),
        solver="baseline",
        workers=2,
        params={"spread_slice": 2, "spread_attempts": 8, "shrink_rounds": 5},
        budget=Budget(seconds=60),
    )
    assert result.outcome == "complete" and result.assessment.valid


def route_refusals_of_an_insertion(net_failures: int) -> tuple[int, bool]:
    """How many route refusals the insertion of ``y`` meets behind a wall reserved for another carrier, and whether it placed."""
    ctx = placed_context()
    world = ctx.world
    net = next(
        n for n in world.netlist.nets.values() if any(r.cell == "y" for r in n.pins())
    )
    layer = world.carrier_layer(net.carrier)
    wall = [(12, y) for y in range(world.fabric.height)]
    assert ctx.attempt(lambda b: b.reserve("wall", layer, wall, "other")).ok
    search = Search(
        ctx, {"candidates": 12, "gap": 1, "lookahead": 1, "net_failures": net_failures}
    )
    search.proposals.reset(1)
    anchors = search.proposals.ranked("y", 0, random.Random(1))
    before = len(ctx.refusals)
    result = ctx.attempt(lambda b: search.insert(b, "y", anchors), strict=False)
    assert result.ok
    routed = [r for r in ctx.refusals[before:] if r.stage == "route"]
    return len(routed), "y" in world.placements


def test_an_insertion_gives_a_cell_up_after_route_failures_on_one_net() -> None:
    every, placed_every = route_refusals_of_an_insertion(0)
    two, placed_two = route_refusals_of_an_insertion(2)
    assert not placed_every and not placed_two
    assert two == 2 and every > 2
