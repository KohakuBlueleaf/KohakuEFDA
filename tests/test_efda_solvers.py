"""The project's solver: registered under the framework, a legal client of the pack, its search carrying the project's rules."""

import random
from pathlib import Path

import pytest

from kohakuefda.layout.settings import DESCRIPTIONS, SOLVER_NAMES, SOLVERS, framework_id
from kohakuefda.layout.stages import netlist_stage, plan_stage
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.scenario import Scenario
from kohakuefda.physics import EndfieldPhysics
from kohakuefda.physics.facts import lane_facts
from kohakuefda.solvers import SOLVER_IDS, EndfieldProposals, EndfieldSearch
from kohakuefda.solvers.guided import GuidedLayout
from kohakuefda.solvers.search import GUIDED, RESEATED, GuidedSearch, embed
from kohakuefda.synth import problem_of
from kohakuefda.synth.problem import board_of
from kohakulayout.engine import Context
from kohakulayout.solvers import get, known, level3
from kohakulayout.solvers.regional.search import DEFAULTS as FRAMEWORK_DEFAULTS
from kohakulayout.state import World
from tests.test_endfield_pack import wuling_toy

ROOT = Path(__file__).resolve().parents[1]
FRAMEWORK = {"baseline", "regional", "climb", "anneal", "floorplan", "inorder"}


def test_every_shipped_solver_is_catalogued_with_a_description() -> None:
    assert SOLVER_IDS == ("endfield.guided",) and set(SOLVER_IDS) <= set(known())
    assert set(SOLVER_NAMES) == FRAMEWORK | {"guided"}
    assert next(iter(SOLVER_NAMES)) == "guided"
    assert set(DESCRIPTIONS) == set(SOLVER_NAMES)
    assert framework_id("guided") == GuidedLayout.id
    for name, solver_id in SOLVER_NAMES.items():
        entry = SOLVERS.get(name).describe()
        assert entry["id"] == solver_id
        declared = {p.name: p for p in get(solver_id).params}
        assert set(entry["defaults"]) == set(entry["parameter_types"]) == set(declared)
        assert entry["choices"] == {
            p.name: list(p.choices) for p in declared.values() if p.choices
        }


def test_the_guided_search_carries_the_projects_rules() -> None:
    assert EndfieldSearch.defaults["extent_weight"] == 0.0
    assert EndfieldSearch.defaults["lookahead"] == 1
    assert "origin_weight" not in EndfieldSearch.defaults
    assert FRAMEWORK_DEFAULTS["lookahead"] == 3
    assert EndfieldSearch.proposer is EndfieldProposals
    assert GuidedSearch.defaults is GUIDED and GuidedSearch.reseated == RESEATED
    solver = get(GuidedLayout.id)
    assert solver.search is GuidedSearch
    defaults = {p.name: p.default for p in solver.params}
    assert defaults["seed_kind"] == "lines" and defaults["acceptance"] == "climb"
    assert defaults["reseat_every"] == 12 and defaults["adaptive_moves"] is True
    assert defaults["batch_moves"] is True and defaults["candidates"] == 80


@pytest.mark.parametrize("seed_kind", ["lines", "regional"])
def test_guided_is_a_legal_client_on_the_pack(seed_kind: str) -> None:
    params = {
        "seed_kind": seed_kind,
        "construction_steps": 8,
        "improvement_steps": 10,
        "until_budget": False,
    }
    report = level3(
        GuidedLayout.id, {"endfield": wuling_toy}, params=params, units=4000
    )
    assert report.failures == [], report.failures


def test_a_free_depot_part_is_offered_the_corner_lattice() -> None:
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


def test_the_seed_search_draws_its_jitter_from_the_raw_seed() -> None:
    problem = wuling_toy()
    ctx = Context(problem, EndfieldPhysics(), seed=7, router=None)
    search = EndfieldSearch(ctx)
    assert search.rng.random() == random.Random(7).random()
    assert list(search.cells) == list(problem.netlist.cells)
    assert list(ctx.world.netlist.cells) == sorted(problem.netlist.cells)


def test_the_embedding_places_every_laned_cell_in_the_box_with_partners_near() -> None:
    dataset = Dataset.load(ROOT / "data/1.5.3@9764758-3/dataset.json")
    scenario = Scenario.from_toml(ROOT / "tests/fixtures/scenario_valley_battery.toml")
    netlist = netlist_stage(dataset, scenario, plan_stage(dataset, scenario))
    world = World(
        problem_of(dataset, netlist, board_of(dataset, scenario)), EndfieldPhysics()
    )
    proposals = EndfieldProposals(world, dict(EndfieldSearch.defaults))
    places = proposals.places
    x0, y0, x1, y1 = proposals.box
    assert places and all(x0 <= x < x1 and y0 <= y < y1 for x, y in places.values())
    pairs = [
        (s, t)
        for net in world.netlist.nets.values()
        for (s, _), (t, _), _ in lane_facts(net)
        if s in places and t in places and s != t
    ]
    assert pairs

    def span(a: str, b: str) -> float:
        return abs(places[a][0] - places[b][0]) + abs(places[a][1] - places[b][1])

    names = sorted(places)
    every = [span(a, b) for i, a in enumerate(names) for b in names[i + 1 :]]
    laned = [span(a, b) for a, b in pairs]
    assert sum(laned) / len(laned) < sum(every) / len(every)
    assert embed(pairs, proposals.box) == places
