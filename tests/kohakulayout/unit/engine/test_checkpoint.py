"""Checkpoints: the JSON artifact, save and load, and resuming into a fresh context."""

from pathlib import Path

from kohakulayout.engine import Budget, Context
from kohakulayout.engine.checkpoint import Checkpoint, load, save
from kohakulayout.templates.physics.null import problem


def test_checkpoint_round_trips_and_resumes(tmp_path: Path) -> None:
    ctx = Context(problem(), router=None, budget=Budget(units=100), seed=5)
    ctx.solver, ctx.params = "inorder", {"tries": 3}
    ctx.attempt(lambda b: b.place("box", (0, 0)))
    ctx.attempt(lambda b: b.place("t1", (4, 4)))
    ctx.consider()
    drawn = ctx.rng.random()
    checkpoint = ctx.checkpoint()
    assert (
        checkpoint.attempts == 2
        and checkpoint.accepts == 1
        and checkpoint.budget["used"] == 2
    )
    path = save(checkpoint, tmp_path / "cp" / "1.json")
    loaded = load(path)
    assert (
        isinstance(loaded, Checkpoint)
        and loaded.layout.digest() == checkpoint.layout.digest()
    )
    fresh = Context(problem(), router=None, budget=Budget(units=100), seed=99)
    fresh.resume(loaded)
    assert fresh.world.digest() == ctx.world.digest()
    assert (
        fresh.budget.used == 2
        and fresh.solver == "inorder"
        and fresh.params == {"tries": 3}
    )
    assert fresh.best is not None and fresh.best_assessment.metrics["placed"] == 2
    assert fresh.rng.random() == ctx.rng.random()
    assert drawn != fresh.rng.random()
