"""The service: how a solve is started, watched, stopped, saved and resumed; local and process implementations."""

from kohakulayout.service.events import JsonlSink, read_events
from kohakulayout.service.local import LocalService
from kohakulayout.service.process import ProcessService
from kohakulayout.service.protocol import (
    FINAL,
    EventFilter,
    Request,
    RunId,
    RunResult,
    RunState,
    RunStatus,
    SolveService,
)
from kohakulayout.service.runs import RunDir, list_runs, new_run_id

__all__ = [
    "FINAL",
    "EventFilter",
    "JsonlSink",
    "LocalService",
    "ProcessService",
    "Request",
    "RunDir",
    "RunId",
    "RunResult",
    "RunState",
    "RunStatus",
    "SolveService",
    "list_runs",
    "new_run_id",
    "read_events",
]
