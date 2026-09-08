"""The in-order solver on gates and null, the parameter schema and the registry."""

import pytest

from kohakulayout.engine import Context
from kohakulayout.errors import SolverError
from kohakulayout.solvers import BaseSolver, InOrder, Param, Solver, get, known, resolve
from kohakulayout.state import StateCheck
from kohakulayout.templates.physics.gates import (
    from_expressions,
    problem,
    random_circuit,
)
from kohakulayout.templates.physics.gates.boundaries import edge_side, touches
from kohakulayout.templates.physics.null import problem as null_problem


def test_params_resolve_and_refuse() -> None:
    declared = (
        Param(name="tries", type="int", default=8),
        Param(name="mode", type="choice", default="fast", choices=("fast", "slow")),
        Param(name="on", type="bool", default=False),
    )
    assert resolve(declared, {"tries": "3", "on": "yes"}) == {
        "tries": 3,
        "mode": "fast",
        "on": True,
    }
    with pytest.raises(SolverError, match="unknown parameter"):
        resolve(declared, {"nope": 1})
    with pytest.raises(SolverError, match="not one of"):
        resolve(declared, {"mode": "medium"})


def test_registry_knows_inorder() -> None:
    assert "inorder" in known()
    solver = get("inorder")
    assert isinstance(solver, InOrder) and isinstance(solver, Solver)
    with pytest.raises(SolverError, match="no solver"):
        get("nowhere")


def test_inorder_places_gates_on_their_edges() -> None:
    netlist = from_expressions(["s = a ^ b", "c = a & b"])
    check = StateCheck()
    ctx = Context(problem(netlist, width=24, height=12), checker=check, router=None)
    assert get("inorder").run(ctx) == "incomplete"
    world = ctx.world
    assert set(world.placements) == set(netlist.cells)
    for cell_id, placement in world.placements.items():
        side = edge_side(netlist.cells[cell_id])
        assert side is None or touches(world, placement, side)
    assessment = ctx.assess()
    assert assessment.metrics["missing"] == 0
    assert assessment.metrics["unrouted"] == len(netlist.nets)
    assert not assessment.complete
    assert check.failures == []


def test_inorder_is_reproducible_and_bounded() -> None:
    netlist = random_circuit(11, inputs=4, gates=12)
    digests = set()
    for _ in range(2):
        ctx = Context(problem(netlist, width=40, height=20), seed=1, router=None)
        get("inorder").run(ctx, tries=16)
        digests.add(ctx.world.digest())
    assert len(digests) == 1
    small = Context(problem(netlist, width=8, height=6), router=None)
    solver = get("inorder")
    assert solver.run(small, tries=4) == "incomplete"
    assert small.assess().metrics["missing"] > 0
    assert all(r.stage for r in solver.refusals)


def test_base_solver_outcome_follows_the_world() -> None:
    class Nothing(BaseSolver):
        id = "nothing"

    ctx = Context(null_problem())
    assert Nothing().run(ctx) == "incomplete"
    with pytest.raises(SolverError):
        Nothing().run(ctx, tries=1)
