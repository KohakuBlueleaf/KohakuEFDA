"""One workflow: a run starved of budget, checkpointed, resumed with more, and graded."""

from kohakulayout.engine import Budget, Context, ListSink
from kohakulayout.engine.plugins import CheckpointPlugin, default_plugins
from kohakulayout.solvers import get
from kohakulayout.state import StateCheck
from kohakulayout.templates.physics.gates import from_expressions, problem


class TestEngineResume:
    def test_starve_checkpoint_resume_finish(self) -> None:
        prob = problem(
            from_expressions(["s = a ^ b", "c = a & b"]), width=32, height=16
        )
        sink = ListSink()
        starved = Context(
            prob,
            seed=3,
            budget=Budget(units=6),
            progress=sink,
            checker=StateCheck(),
            plugins=(*default_plugins(), CheckpointPlugin(every_accepts=1)),
        )
        outcome = get("inorder").run(starved)
        assert outcome == "incomplete" and starved.budget.used <= 7
        assert any("units" in e.payload["message"] for e in sink.of("log"))
        checkpoint = starved.checkpoints[-1]
        assert checkpoint.layout.placements

        resumed = Context(
            prob,
            seed=3,
            budget=Budget(units=800),
            checker=StateCheck(),
            progress=ListSink(),
        )
        resumed.resume(checkpoint)
        assert resumed.world.placements.keys() == checkpoint.layout.placements.keys()
        assert get("inorder").run(resumed) == "complete"
        assessment = resumed.best_assessment
        assert assessment is not None and assessment.valid
        assert resumed.best_layout().check_against(prob.netlist, prob.fabric) == []
        assert any(
            e.payload["message"] == "resumed" for e in resumed.progress.of("log")
        )
