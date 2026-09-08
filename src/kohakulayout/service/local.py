"""The local service: the engine in the caller's process, every artifact under a run directory."""

import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from kohakulayout.engine import Budget, Context, make_execution
from kohakulayout.engine.checkpoint import Checkpoint
from kohakulayout.engine.plugins import CheckpointPlugin, EnginePlugin, default_plugins
from kohakulayout.engine.progress import Event, NullSink
from kohakulayout.errors import Cancelled, KohakuLayoutError, ServiceError
from kohakulayout.ir import Layout, Problem
from kohakulayout.physics import get as get_physics
from kohakulayout.physics import locate, path_of, register
from kohakulayout.pipeline.passes import PassManager
from kohakulayout.service.events import JsonlSink, read_events
from kohakulayout.service.protocol import (
    EventFilter,
    Request,
    RunId,
    RunResult,
    RunStatus,
)
from kohakulayout.service.runs import RunDir, list_runs, new_run_id
from kohakulayout.solvers import get


class RunRecorder(EnginePlugin):
    """Keeps the run directory current: status on every accept and checkpoint, the best layout as it improves."""

    name = "recorder"
    priority = 90

    def __init__(self, run: RunDir, status: RunStatus) -> None:
        self.run = run
        self.status = status

    def refresh(self, ctx: Any, state: str | None = None) -> None:
        status = self.status
        if state is not None:
            status.state = state
        status.phase = ctx.phase
        status.budget_used = ctx.budget.used
        status.attempts, status.accepts, status.seq = ctx.attempts, ctx.accepts, ctx.seq
        if ctx.best_assessment is not None:
            status.best_metrics = dict(ctx.best_assessment.metrics)
        self.run.write_status(status)

    def pre_attempt(self, ctx: Any, attempt: Any) -> Any:
        if self.run.cancelled():
            raise Cancelled(f"run {self.run.run} was cancelled")
        return None

    def post_accept(self, ctx: Any, token: Any, assessment: Any) -> None:
        self.run.write_best(ctx.best_layout(), assessment)
        self.refresh(ctx)

    def on_checkpoint(self, ctx: Any, checkpoint: Checkpoint) -> None:
        self.run.write_checkpoint(checkpoint)
        self.refresh(ctx)


class LocalService:
    """Runs synchronously on ``submit``; a cancel from a sink callback or another thread lands at the next attempt."""

    def __init__(self, root: Path, workers: int = 1, sink: Any = None) -> None:
        self.root = Path(root)
        self.workers = workers
        self.sink = sink

    def submit(self, problem: Problem, request: Request) -> RunId:
        request = with_physics(problem, request)
        run_id = new_run_id(self.root, problem, request)
        RunDir(self.root, run_id).create(problem, request)
        self.run_now(run_id)
        return run_id

    def run_now(self, run_id: RunId, checkpoint: Checkpoint | None = None) -> RunStatus:
        run = RunDir(self.root, run_id)
        problem, request = run.problem(), run.request()
        status = RunStatus(run=run_id, state="running")
        run.write_status(status)
        log = JsonlSink(run.events_path) if request.log_events else None
        sink = _Tee(log, self.sink)
        recorder = RunRecorder(run, status)
        plugins = (
            *default_plugins(),
            CheckpointPlugin(every_accepts=request.checkpoint_every),
            recorder,
        )
        try:
            if request.physics:
                register(locate(request.physics))
            problem = PassManager().run(problem)
            ctx = Context(
                problem,
                seed=request.seed,
                router=request.router,
                budget=Budget(units=request.units, seconds=request.seconds),
                plugins=plugins,
                progress=sink,
                run=run_id,
                execution=make_execution(self.workers),
            )
            if checkpoint is not None:
                ctx.resume(checkpoint)
            outcome = get(request.solver).run(ctx, **request.params)
            status.outcome = outcome
            self._finish(
                run, recorder, ctx, "done" if outcome == "complete" else "incomplete"
            )
        except Cancelled as exc:
            status.error = str(exc)
            self._finish(run, recorder, ctx, "cancelled")
        except KohakuLayoutError as exc:
            status.state, status.error = "failed", str(exc)
            run.write_status(status)
        finally:
            if log is not None:
                log.close()
        return run.status()

    def _finish(
        self, run: RunDir, recorder: RunRecorder, ctx: Context, state: str
    ) -> None:
        if ctx.best_assessment is not None:
            run.write_best(ctx.best_layout(), ctx.best_assessment)
        recorder.refresh(ctx, state)
        ctx.emit("status", {"state": state, "outcome": recorder.status.outcome})

    # ------------------------------------------------------------- reads
    def status(self, run: RunId) -> RunStatus:
        target = RunDir(self.root, run)
        if not target.exists():
            raise ServiceError(f"no run {run!r} under {self.root}")
        return target.status()

    def events(self, run: RunId, filter: EventFilter | None = None) -> Iterator[Event]:
        return read_events(RunDir(self.root, run).events_path, filter)

    def cancel(self, run: RunId) -> None:
        RunDir(self.root, run).request_cancel()

    def result(self, run: RunId) -> RunResult:
        target = RunDir(self.root, run)
        status = self.status(run)
        best = target.best()
        return RunResult(
            run=run,
            state=status.state,
            outcome=status.outcome,
            layout=best[0] if best else None,
            assessment=best[1] if best else None,
            checkpoints=target.checkpoints(),
            error=status.error,
        )

    def best(self, run: RunId) -> Layout | None:
        best = RunDir(self.root, run).best()
        return best[0] if best else None

    def resume(self, checkpoint: Checkpoint, request: Request) -> RunId:
        """A new run continuing from ``checkpoint``; the parent run's problem is the problem."""
        parent = RunDir(self.root, checkpoint.run)
        if not parent.exists():
            raise ServiceError(
                f"cannot resume: no run {checkpoint.run!r} under {self.root}"
            )
        problem = parent.problem()
        request = with_physics(
            problem,
            request.model_copy(
                update={"parent": checkpoint.run, "parent_checkpoint": checkpoint.seq}
            ),
        )
        run_id = new_run_id(self.root, problem, request)
        RunDir(self.root, run_id).create(problem, request)
        self.run_now(run_id, checkpoint)
        return run_id

    def wait(self, run: RunId, timeout: float | None = None) -> RunStatus:
        return self.status(run)

    def runs(self) -> tuple[RunStatus, ...]:
        return list_runs(self.root)


def with_physics(problem: Problem, request: Request) -> Request:
    """The request names the physics class, so a worker process can rebuild the pack without a registry."""
    if request.physics:
        return request
    return request.model_copy(update={"physics": path_of(get_physics(problem.physics))})


class _Tee:
    def __init__(self, *sinks: Any) -> None:
        self.sinks = [s for s in sinks if s is not None] or [NullSink()]

    def emit(self, event: Event) -> None:
        for sink in self.sinks:
            sink.emit(event)


def elapsed_since(start: float) -> float:
    return time.monotonic() - start


__all__ = ["LocalService", "RunRecorder"]
