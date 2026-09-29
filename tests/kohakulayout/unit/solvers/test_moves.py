"""Layout moves: reseating a constrained cell among its anchors, adaptive operator draws, batch relocation."""

import random

from kohakulayout.engine import Context
from kohakulayout.ir import Constraint
from kohakulayout.physics.protocol import Anchor
from kohakulayout.solvers.local.climb import PARAMS
from kohakulayout.solvers.local.moves import LayoutMoves
from kohakulayout.solvers.params import resolve
from kohakulayout.solvers.regional.search import Search
from kohakulayout.templates.physics.null import problem

PLACED = {"t1": (0, 0), "s1": (4, 0), "box": (0, 3), "c": (6, 6)}


class Seated(Search):
    reseated = frozenset({"seat"})


def seated_context() -> Context:
    base = problem()
    cells = dict(base.netlist.cells)
    cells["c"] = cells["c"].model_copy(update={"constraint": Constraint(kind="seat")})
    netlist = base.netlist.model_copy(update={"cells": cells})
    ctx = Context(base.model_copy(update={"netlist": netlist}))
    anchors = {c: Anchor(x=x, y=y) for c, (x, y) in PLACED.items()}
    assert ctx.attempt(lambda b: b.place_batch(anchors)).ok
    return ctx


def settings(**given) -> dict:
    return resolve(PARAMS, given)


def test_reseat_moves_a_constrained_cell_to_another_of_its_anchors() -> None:
    ctx = seated_context()
    moves = LayoutMoves(ctx, settings(reseat_every=1, reseat_candidates=3), Seated)
    assert moves.propose() == ("reseat", None), "paired, but c shares no net"
    landed = False
    for _ in range(16):
        name, body = moves.propose()
        assert name == "reseat"
        landed = body is not None and ctx.attempt(body).ok
        if landed:
            break
    assert landed
    moved = ctx.world.placements["c"]
    assert (moved.x, moved.y) != PLACED["c"]
    assert all(
        (ctx.world.placements[c].x, ctx.world.placements[c].y) == xy
        for c, xy in PLACED.items()
        if c != "c"
    )


def test_reseat_offers_nothing_without_reseated_kinds() -> None:
    ctx = seated_context()
    moves = LayoutMoves(ctx, settings(reseat_every=1), Search)
    assert moves.propose() == ("reseat", None)


def test_adaptive_draws_follow_the_credited_operator() -> None:
    ctx = seated_context()
    moves = LayoutMoves(ctx, settings(adaptive_moves=True, repack_every=0), Search)
    assert moves.selection is not None
    names = list(moves.by_name)
    for name in names:
        moves.feedback(name, -1.0 if name == "swap" else None, name == "swap", 1)
    moves.selection.exploration = 0.0
    moves.rng = moves.selection.rng = random.Random(0)
    drawn = [moves.selection.choose() for _ in range(20)]
    assert set(drawn) == {"swap"}
    uniform = LayoutMoves(ctx, settings(), Search)
    assert uniform.selection is None


def test_a_cluster_lands_one_by_one_and_as_a_batch() -> None:
    for batch in (False, True):
        ctx = seated_context()
        moves = LayoutMoves(ctx, settings(batch_moves=batch), Search)
        _, body = moves._relocation("cluster", {"t1": (0, 1, 0), "s1": (4, 1, 0)})
        assert ctx.attempt(body).ok
        placed = ctx.world.placements
        assert (placed["t1"].y, placed["s1"].y) == (1, 1)
        assert set(ctx.world.wires) == {"n1"}
