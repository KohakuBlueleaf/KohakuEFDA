"""The default occupant of every physics hook, the chain and the registry."""

from fractions import Fraction

import pytest

from kohakulayout.errors import PhysicsError
from kohakulayout.ir import Cell, Finding, Footprint, Layout, Refusal
from kohakulayout.physics import (
    BasePhysics,
    DefaultCarriers,
    DefaultFlow,
    DefaultObjective,
    Emitter,
    FunctionRule,
    Occupant,
    Reach,
    diagnose,
    edge_cells,
    energy,
    free_anchors,
    get,
    known,
    reach_cells,
    run_rules,
    satisfied,
)
from kohakulayout.state import World
from kohakulayout.templates.physics.null import problem as null_problem


def test_default_carriers_are_exclusive() -> None:
    carriers = DefaultCarriers()
    assert (
        carriers.may_share(
            Occupant(kind="wire", carrier="wire"), Occupant(kind="wire", carrier="wire")
        )
        is False
    )
    assert carriers.crossing("wire", "wire").mode == "forbidden"
    assert carriers.junction("wire").mode == "forbidden"
    assert carriers.run_limit("wire") is None
    assert carriers.repeater("wire") is None
    assert carriers.transfers_through("bridge", "wire") is False


def test_default_flow_splits_evenly_and_merges_to_capacity() -> None:
    flow = DefaultFlow()
    assert flow.split(Fraction(30), 3) == (Fraction(10),) * 3
    assert sum(flow.merge((Fraction(20), Fraction(20)), Fraction(30))) == Fraction(30)
    assert flow.merge((Fraction(5), Fraction(5)), None) == (Fraction(5), Fraction(5))
    assert flow.stateful() is False


def test_diagnose_picks_the_earliest_stage_and_names_the_empty_case() -> None:
    late = Refusal(stage="route", subject="net:n1")
    early = Refusal(stage="region", subject="cell:g1")
    assert diagnose((late, early)) is early
    assert diagnose(()).stage == "legal"
    custom = Refusal(stage="zone", subject="cell:g1")
    assert diagnose((custom, late), order=("zone", "route")) is custom
    assert diagnose((custom, late)) is late


def test_rules_run_in_order_and_fill_the_rule_id() -> None:
    def hot(world: object, layout: Layout, metrics: dict) -> list[Finding]:
        return [
            Finding(rule="", severity="warning", message="too hot", subject="cell:g1")
        ]

    rules = (
        FunctionRule("R1", "warning", hot, attrs={"pack": {"note": 1}}),
        FunctionRule("R2", "error", lambda w, l, m: []),
    )
    findings = run_rules(rules, None, Layout(), {})
    assert [f.rule for f in findings] == ["R1"]
    assert findings[0].attrs == {"pack": {"note": 1}}


def test_energy_weights_only_named_metrics() -> None:
    objective = DefaultObjective()
    assert energy(objective, {"area": 12, "units": 3, "wire_cells": 99}) == Fraction(15)
    objective.weights = {"area": Fraction(1, 2)}
    assert energy(objective, {"area": 12}) == Fraction(6)


def test_reach_and_satisfied() -> None:
    emitter = Emitter(
        kind="power",
        footprint=Footprint(id="P", width=1, height=1),
        reach=Reach(radius=1),
    )
    cells = reach_cells(emitter, 5, 5)
    assert (4, 4) in cells and (6, 6) in cells and (7, 5) not in cells
    assert satisfied(((5, 5), (9, 9)), cells, partial=True)
    assert not satisfied(((5, 5), (9, 9)), cells, partial=False)
    masked = Emitter(
        kind="p",
        footprint=emitter.footprint,
        reach=Reach(shape="mask", cells=((0, 0), (1, 0))),
    )
    assert reach_cells(masked, 2, 3) == frozenset({(2, 3), (3, 3)})


def test_free_anchors_and_edges_follow_the_fabric() -> None:
    problem = null_problem(width=4, height=3)
    world = World(problem, get(problem.physics))
    anchors = list(free_anchors(world, world.netlist.cells["box"]))
    assert len(anchors) == 3 * 2
    assert all(a.rot == 0 for a in anchors)
    assert edge_cells(world, "N") == ((0, 0), (1, 0), (2, 0), (3, 0))
    assert edge_cells(world, "E") == ((3, 0), (3, 1), (3, 2))


def test_registry_names_the_unknown_pack() -> None:
    assert "null" in known()
    assert get("null@1").ref == "null@1"
    with pytest.raises(PhysicsError, match="no physics pack 'nowhere'"):
        get("nowhere")


def test_base_physics_requires_fabric_and_library() -> None:
    class Bare(BasePhysics):
        id = "bare"

    with pytest.raises(NotImplementedError):
        Bare().fabric({})
    with pytest.raises(NotImplementedError):
        Bare().library()
    assert Bare().unit_footprints() == {}
    assert Bare().fields.needs(Cell(id="x", footprint="F")) == ()
