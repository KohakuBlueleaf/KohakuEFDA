"""The process service: each solve in a worker process, the same protocol, status read from the run directory."""

import multiprocessing
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from kohakulayout.engine.checkpoint import Checkpoint
from kohakulayout.engine.progress import Event
from kohakulayout.errors import NotAvailable, ServiceError
from kohakulayout.ir import Layout, Problem
from kohakulayout.service.local import LocalService, with_physics
from kohakulayout.service.protocol import (
    EventFilter,
    Request,
    RunId,
    RunResult,
    RunStatus,
)
from kohakulayout.service.runs import RunDir, new_run_id


def worker_main(root: str, run_id: str, checkpoint_json: str | None) -> None:
    """The worker's whole life: run one run under ``root``; packs register through the physics registry."""
    checkpoint = Checkpoint.from_json(checkpoint_json) if checkpoint_json else None
    LocalService(Path(root)).run_now(run_id, checkpoint)


class ProcessService:
    """Submits return at once; ``wait`` joins the worker; cancel is a flag the worker sees at its next attempt."""

    def __init__(self, root: Path, method: str = "spawn") -> None:
        self.root = Path(root)
        self.method = method
        self.local = LocalService(self.root)
        self.processes: dict[RunId, Any] = {}

    def _start(self, run_id: RunId, checkpoint: Checkpoint | None = None) -> None:
        try:
            context = multiprocessing.get_context(self.method)
            process = context.Process(
                target=worker_main,
                args=(
                    str(self.root),
                    run_id,
                    checkpoint.to_json() if checkpoint else None,
                ),
                daemon=True,
            )
            process.start()
        except (OSError, RuntimeError, ValueError) as exc:
            raise NotAvailable(
                f"worker processes are not available ({exc}); use LocalService to run in process"
            ) from exc
        self.processes[run_id] = process

    def submit(self, problem: Problem, request: Request) -> RunId:
        request = with_physics(problem, request)
        run_id = new_run_id(self.root, problem, request)
        RunDir(self.root, run_id).create(problem, request)
        self._start(run_id)
        return run_id

    def status(self, run: RunId) -> RunStatus:
        status = self.local.status(run)
        process = self.processes.get(run)
        if process is not None and not process.is_alive() and not status.final:
            status.state, status.error = (
                "failed",
                f"worker exited with code {process.exitcode}",
            )
            RunDir(self.root, run).write_status(status)
        return status

    def events(self, run: RunId, filter: EventFilter | None = None) -> Iterator[Event]:
        return self.local.events(run, filter)

    def cancel(self, run: RunId) -> None:
        self.local.cancel(run)

    def result(self, run: RunId) -> RunResult:
        return self.local.result(run)

    def best(self, run: RunId) -> Layout | None:
        return self.local.best(run)

    def resume(self, checkpoint: Checkpoint, request: Request) -> RunId:
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
        self._start(run_id, checkpoint)
        return run_id

    def wait(self, run: RunId, timeout: float | None = None) -> RunStatus:
        process = self.processes.get(run)
        if process is not None:
            process.join(timeout)
        deadline = time.monotonic() + (timeout if timeout is not None else 3600.0)
        while not self.status(run).final and time.monotonic() < deadline:
            time.sleep(0.02)
        return self.status(run)

    def close(self) -> None:
        for process in self.processes.values():
            if process.is_alive():
                process.terminate()
            process.join(5)


__all__ = ["ProcessService", "worker_main"]
