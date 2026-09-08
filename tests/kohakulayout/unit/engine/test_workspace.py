"""The workspace: an oversized board, the target in its middle, overflow and projection."""

from kohakulayout.engine import Context, Workspace
from kohakulayout.templates.physics.gates import GatesPhysics, from_expressions, problem


def test_workspace_projects_back_onto_the_target() -> None:
    origin = problem(from_expressions("y = a & b"), width=12, height=8)
    space = Workspace(origin, GatesPhysics(), scale=2)
    assert (space.problem.fabric.width, space.problem.fabric.height) == (24, 16)
    assert (space.target.x, space.target.y, space.target.w, space.target.h) == (
        6,
        4,
        12,
        8,
    )
    ctx = Context(space.problem, router=None)
    assert ctx.attempt(lambda b: b.place("g1", (8, 6))).ok
    layout = ctx.layout()
    assert space.overflow(layout) == 0
    projected = space.project(layout)
    assert (projected.placements["g1"].x, projected.placements["g1"].y) == (2, 2)
    assert projected.problem == origin.digest()
    assert space.publish(layout) is not None
    assert ctx.attempt(lambda b: b.place("a", (0, 0))).ok
    assert space.overflow(ctx.layout()) == 1 and space.publish(ctx.layout()) is None
