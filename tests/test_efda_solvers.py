"""The project's own solvers: registered under the framework, carrying the engine's construction rules, legal clients of the pack."""

import pytest

from kohakuefda.layout.settings import SOLVERS, framework_id
from kohakuefda.solvers import SOLVER_IDS, EndfieldProposals, EndfieldSearch
from kohakulayout.solvers import get, known, level3
from kohakulayout.solvers.regional.search import DEFAULTS as FRAMEWORK_DEFAULTS
from tests.test_endfield_pack import wuling_toy


def test_the_project_solvers_are_registered_with_the_engines_rules() -> None:
    assert set(SOLVER_IDS) <= set(known())
    assert framework_id("hc") == "endfield.climb"
    assert framework_id("regional") == "endfield.regional"
    assert EndfieldSearch.defaults["extent_weight"] == 0.0
    assert EndfieldSearch.defaults["lookahead"] == 1
    assert "origin_weight" not in EndfieldSearch.defaults
    assert (
        FRAMEWORK_DEFAULTS["lookahead"] == 3
        and FRAMEWORK_DEFAULTS["extent_weight"] == 1.0
    )
    assert EndfieldSearch.proposer is EndfieldProposals
    assert get("endfield.climb").search is EndfieldSearch
    assert SOLVERS.get("hc").defaults["until_budget"] is True


@pytest.mark.parametrize("solver", ["endfield.regional", "endfield.climb"])
def test_a_project_solver_is_a_legal_client_on_the_pack(solver: str) -> None:
    params = (
        {"attempts": 8, "shrink_rounds": 5}
        if solver == "endfield.regional"
        else {"construction_steps": 8, "improvement_steps": 10, "until_budget": False}
    )
    report = level3(solver, {"endfield": wuling_toy}, params=params, units=4000)
    assert report.failures == [], report.failures


def test_a_free_depot_part_is_offered_the_engines_corner_lattice() -> None:
    from kohakuefda.physics import EndfieldPhysics
    from kohakulayout.state import World

    world = World(wuling_toy(), EndfieldPhysics())
    proposals = EndfieldProposals(world, {"depot_step": 2, "depot_window": 8})
    part = next(
        c.id
        for c in world.netlist.cells.values()
        if c.kind == "depot" and c.constraint.kind == "cluster"
    )
    rows = {tuple(r) for r in proposals.fitting(part).tolist()}
    x0, y0, _, _ = proposals.box
    fp = world.footprint_of(part)
    assert rows == {
        (x0 + dx, y0 + dy, rot)
        for dy in (2, 4, 6)
        for dx in (2, 4, 6)
        for rot in fp.rotations
    }
    other = next(c.id for c in world.netlist.cells.values() if c.kind != "depot")
    assert len(proposals.fitting(other)) > len(rows)


def test_the_search_draws_its_jitter_as_the_engine_did() -> None:
    import random

    from kohakuefda.physics import EndfieldPhysics
    from kohakulayout.engine import Context

    problem = wuling_toy()
    ctx = Context(problem, EndfieldPhysics(), seed=7, router=None)
    search = EndfieldSearch(ctx)
    assert search.rng.random() == random.Random(7).random()
    assert list(search.cells) == list(problem.netlist.cells)
    assert list(ctx.world.netlist.cells) == sorted(problem.netlist.cells)
