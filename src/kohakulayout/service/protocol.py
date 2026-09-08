"""The service protocol: how a solve is started, watched, stopped, saved and resumed."""

from collections.abc import Iterator
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel

from kohakulayout.engine.checkpoint import Checkpoint
from kohakulayout.engine.progress import Event
from kohakulayout.ir import Assessment, Layout, Model, Problem

RunId = str
RunState = Literal["queued", "running", "done", "incomplete", "failed", "cancelled"]
FINAL: frozenset[str] = frozenset({"done", "incomplete", "failed", "cancelled"})


class Request(Model):
    solver: str = "inorder"
    params: dict[str, Any] = {}
    seed: int = 0
    units: int | None = None
    seconds: float | None = None
    router: str = "default"
    physics: str = ""
    checkpoint_every: int = 1
    log_events: bool = True
    parent: str | None = None
    parent_checkpoint: int | None = None


class RunStatus(BaseModel):
    """Mutable on purpose: the recorder rewrites it as the run moves."""

    run: RunId
    state: RunState = "queued"
    phase: str = ""
    budget_used: int = 0
    attempts: int = 0
    accepts: int = 0
    best_metrics: dict[str, Any] = {}
    seq: int = 0
    outcome: str = ""
    error: str = ""

    @property
    def final(self) -> bool:
        return self.state in FINAL


class RunResult(Model):
    run: RunId
    state: RunState
    outcome: str = ""
    layout: Layout | None = None
    assessment: Assessment | None = None
    checkpoints: tuple[Checkpoint, ...] = ()
    error: str = ""


class EventFilter(Model):
    kinds: frozenset[str] | None = None
    every: int = 1

    def admits(self, event: Event, index: int) -> bool:
        if self.kinds is not None and event.kind not in self.kinds:
            return False
        return event.kind != "frame" or self.every <= 1 or index % self.every == 0


@runtime_checkable
class SolveService(Protocol):
    def submit(self, problem: Problem, request: Request) -> RunId: ...
    def status(self, run: RunId) -> RunStatus: ...
    def events(
        self, run: RunId, filter: EventFilter | None = None
    ) -> Iterator[Event]: ...
    def cancel(self, run: RunId) -> None: ...
    def result(self, run: RunId) -> RunResult: ...
    def best(self, run: RunId) -> Layout | None: ...
    def resume(self, checkpoint: Checkpoint, request: Request) -> RunId: ...
    def wait(self, run: RunId, timeout: float | None = None) -> RunStatus: ...


__all__ = [
    "FINAL",
    "EventFilter",
    "Request",
    "RunId",
    "RunResult",
    "RunState",
    "RunStatus",
    "SolveService",
]
