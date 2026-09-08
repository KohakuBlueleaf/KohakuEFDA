"""The solver skeleton and the identity plugin, each with its test."""

from kohakulayout.engine import Budget
from kohakulayout.engine.plugins import default_plugins
from kohakulayout.pipeline import solve
from kohakulayout.solvers import known, level3
from kohakulayout.templates import IdentityPlugin, Skeleton
from kohakulayout.templates.physics.gates import from_expressions, problem
from tests.kohakulayout.unit.solvers.test_level3_inorder import TOYS


def test_skeleton_is_a_registered_solver_that_passes_level3() -> None:
    assert "skeleton" in known() and Skeleton.id == "skeleton"
    report = level3("skeleton", {"gates": TOYS["gates"]}, params={"rounds": 1})
    assert report.failures == [], report.failures


def test_identity_plugin_sees_every_hook_and_changes_nothing() -> None:
    identity = IdentityPlugin()
    prob = problem(from_expressions("y = a & b | ~c"), width=24, height=12)
    with_it = solve(
        prob, plugins=(*default_plugins(), identity), budget=Budget(units=800)
    )
    without = solve(prob, budget=Budget(units=800))
    assert with_it.layout.digest() == without.layout.digest()
    assert {
        "pre_attempt",
        "post_attempt",
        "pre_assess",
        "post_assess",
        "pre_accept",
        "post_accept",
        "on_frame",
        "on_budget",
    } <= set(identity.calls)
