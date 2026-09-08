"""Run directories and the event log."""

from pathlib import Path

from kohakulayout.engine import Context, ListSink
from kohakulayout.engine.progress import Event
from kohakulayout.ir import Frame
from kohakulayout.service import (
    EventFilter,
    JsonlSink,
    Request,
    RunDir,
    RunStatus,
    list_runs,
    new_run_id,
    read_events,
)
from kohakulayout.templates.physics.gates import from_expressions, problem


def test_run_dir_holds_every_artifact(tmp_path: Path) -> None:
    prob = problem(from_expressions("y = a & b"), width=16, height=8)
    request = Request(solver="inorder", seed=3, units=100)
    run_id = new_run_id(tmp_path, prob, request)
    assert run_id.endswith("-inorder-3-0")
    run = RunDir(tmp_path, run_id)
    run.create(prob, request)
    assert run.problem().digest() == prob.digest() and run.request().units == 100
    assert run.status().state == "queued" and not run.cancelled()
    ctx = Context(prob, router=None)
    ctx.attempt(lambda b: b.place("g1", (4, 1)))
    ctx.consider()
    run.write_best(ctx.best_layout(), ctx.best_assessment)
    run.write_checkpoint(ctx.checkpoint())
    run.write_status(RunStatus(run=run_id, state="done", outcome="complete"))
    layout, assessment = run.best()
    assert (
        layout.digest() == ctx.best_layout().digest()
        and assessment.metrics["placed"] == 1
    )
    assert len(run.checkpoints()) == 1 and run.checkpoints()[0].run == ctx.run
    assert [s.state for s in list_runs(tmp_path)] == ["done"]
    assert new_run_id(tmp_path, prob, request).endswith("-inorder-3-1")
    run.request_cancel()
    assert run.cancelled()


def test_event_log_round_trips_and_filters(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    sink = JsonlSink(path)
    listed = ListSink()
    ctx = Context(
        problem(from_expressions("y = a"), width=12, height=6),
        router=None,
        progress=sink,
    )
    for i in range(4):
        ctx.frame(f"step{i}")
    ctx.attempt(lambda b: b.place("a", (5, 5)))
    ctx.log("hello", n=1)
    sink.close()
    events = list(read_events(path))
    assert [e.kind for e in events] == ["frame"] * 4 + ["refusal", "log"]
    assert isinstance(events[0].payload, Frame) and events[0].payload.phase == "step0"
    assert events[-1].payload == {"message": "hello", "n": 1}
    sampled = list(read_events(path, EventFilter(every=2)))
    assert [e.payload.phase for e in sampled if e.kind == "frame"] == ["step0", "step2"]
    only = list(read_events(path, EventFilter(kinds=frozenset({"log"}))))
    assert len(only) == 1
    for event in events:
        listed.emit(
            Event(
                kind=event.kind,
                run=event.run,
                seq=event.seq,
                at=0.0,
                payload=event.payload,
            )
        )
    assert listed.digest()
    assert list(read_events(tmp_path / "missing.jsonl")) == []
