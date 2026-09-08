"""The structural family's parts: representations, the rows decoder, channels, the surrogate, the exact slot."""

import random
from fractions import Fraction
from importlib.resources import files

import pytest

from kohakulayout.engine import Budget, Context
from kohakulayout.errors import NotAvailable, SolverError
from kohakulayout.ir import Netlist
from kohakulayout.solvers import get, known
from kohakulayout.solvers.structural import (
    REPRESENTATIONS,
    Coordinate,
    Rows,
    legalize,
    surrogate,
)
from kohakulayout.solvers.structural import exact as exact_slot
from kohakulayout.solvers.structural.floorplan import items_of
from kohakulayout.solvers.structural.representation import get as get_representation
from kohakulayout.templates.physics.gates import from_expressions, problem


def bank_problem():
    text = (
        files("kohakulayout.templates.physics.gates")
        .joinpath("fixtures/bank.kl")
        .read_text()
    )
    return problem(Netlist.parse(text), width=40, height=12)


def test_registry_and_coordinate_representation() -> None:
    assert {"rows", "coordinate"} <= set(REPRESENTATIONS) and "floorplan" in known()
    with pytest.raises(SolverError, match="no representation"):
        get_representation("nowhere")
    ctx = Context(
        problem(from_expressions("y = a & b"), width=16, height=8), router="default"
    )
    rep = Coordinate()
    structure = rep.initial(ctx, random.Random(0))
    assert set(structure) == set(ctx.world.netlist.cells)
    mutated = rep.mutate(structure, random.Random(1))
    assert sum(1 for c in structure if structure[c] != mutated[c]) == 1
    assert rep.channels(structure, ctx) == [] and set(
        rep.geometry(structure, ctx)
    ) == set(structure)
    assessment = legalize(rep, structure, ctx)
    assert assessment is not None and assessment.metrics["missing"] == 0


def test_rows_decode_channels_and_surrogate_on_the_bank() -> None:
    ctx = Context(bank_problem(), router="default", budget=Budget(units=4000))
    rep = Rows()
    assert items_of(ctx.world) == ["k1", "k2"]
    structure = rep.initial(ctx, random.Random(0))
    assert sum(len(r) for r in structure["rows"]) == 2
    boxes = rep.geometry(structure, ctx)
    assert boxes["k1"][2:] == (15, 2)
    channels = rep.channels(structure, ctx)
    assert channels and all(tag.startswith("channel:") for tag, _, _, _ in channels)
    assert all(carrier == "wire" for _, _, _, carrier in channels)
    estimate = surrogate(rep, structure, ctx)
    assert estimate > 0
    assessment = legalize(rep, structure, ctx)
    assert assessment is not None and assessment.metrics["missing"] == 0
    assert ctx.world.reservations == {}
    assert set(ctx.world.placements) == set(ctx.world.netlist.cells)
    for _ in range(5):
        structure = rep.mutate(structure, random.Random(2))
    assert sum(len(r) for r in structure["rows"]) == 2


def test_surrogate_orders_like_the_assessment() -> None:
    """Two bank floorplans, legalised in either order, rank the same way by surrogate and by area."""
    results = {}
    for order in ("wide-first", "tall-first"):
        ctx = Context(bank_problem(), router="default", budget=Budget(units=8000))
        rep = Rows(rows=1)
        wide = rep.initial(ctx, random.Random(0))
        tall = {
            "rows": [[i] for r in wide["rows"] for i in r],
            "rot": dict(wide["rot"]),
        }
        pairs = [(wide, "wide"), (tall, "tall")]
        if order == "tall-first":
            pairs.reverse()
        for structure, name in pairs:
            assessment = legalize(rep, structure, ctx)
            assert assessment is not None, (order, name)
            results[(order, name)] = (
                surrogate(rep, structure, ctx),
                assessment.metrics["area"],
            )
    assert results[("wide-first", "wide")] == results[("tall-first", "wide")]
    assert results[("wide-first", "tall")] == results[("tall-first", "tall")]
    (s_wide, a_wide), (s_tall, a_tall) = (
        results[("wide-first", "wide")],
        results[("wide-first", "tall")],
    )
    assert (s_wide < s_tall) == (a_wide < a_tall) or a_wide == a_tall


def test_exact_slot_names_its_absence() -> None:
    if not exact_slot.EXACT:
        with pytest.raises(NotAvailable, match="install ortools"):
            exact_slot.get("cpsat")
        return
    occupant = exact_slot.get(min(exact_slot.EXACT))
    placed = occupant.solve(
        {"a": (3, 3), "b": (2, 2), "c": (4, 1)}, (12, 8), seconds=5.0
    )
    assert set(placed) == {"a", "b", "c"}
    with pytest.raises(exact_slot.Infeasible):
        occupant.solve({"a": (20, 20)}, (12, 8), seconds=1.0)


def test_floorplan_params_and_exact_absent() -> None:
    solver = get("floorplan")
    assert solver.resume == "continues"
    ctx = Context(
        problem(from_expressions("y = a & b"), width=16, height=8),
        router="default",
        budget=Budget(units=2000),
    )
    if not exact_slot.EXACT:
        with pytest.raises(NotAvailable):
            solver.run(ctx, exact="cpsat", steps=0)
    assert Fraction(solver.params[-2].default) == Fraction(1, 4)
