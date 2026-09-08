"""The local service: a run recorded, cancelled from a sink, resumed from its checkpoint."""

from pathlib import Path

import pytest

from kohakulayout.engine import CallbackSink
from kohakulayout.errors import ServiceError
from kohakulayout.service import EventFilter, LocalService, Request, SolveService
from kohakulayout.templates.physics.gates import from_expressions, problem


def toy():
    return problem(from_expressions("y = a & b | ~c"), width=24, height=12)


def test_submit_records_a_done_run(tmp_path: Path) -> None:
    service = LocalService(tmp_path)
    assert isinstance(service, SolveService)
    run = service.submit(toy(), Request(solver="inorder", seed=1, units=800))
    status = service.status(run)
    assert status.state == "done" and status.outcome == "complete" and status.final
    assert status.best_metrics["missing"] == 0 and status.budget_used > 0
    result = service.result(run)
    assert result.layout is not None and result.assessment.valid and result.checkpoints
    assert service.best(run).digest() == result.layout.digest()
    kinds = [e.kind for e in service.events(run)]
    assert (
        "frame" in kinds
        and "assessment" in kinds
        and "checkpoint" in kinds
        and kinds[-1] == "status"
    )
    assert (
        list(service.events(run, EventFilter(kinds=frozenset({"status"}))))[-1].payload[
            "state"
        ]
        == "done"
    )
    assert [s.run for s in service.runs()] == [run]
    with pytest.raises(ServiceError, match="no run"):
        service.status("nowhere")


def test_cancel_from_a_sink_and_resume(tmp_path: Path) -> None:
    holder: dict[str, LocalService] = {}
    sink = CallbackSink(
        lambda e: holder["service"].cancel(e.run) if e.kind == "assessment" else None
    )
    service = LocalService(tmp_path, sink=sink)
    holder["service"] = service
    run = service.submit(
        toy(),
        Request(
            solver="climb",
            seed=2,
            params={"improvement_steps": 400, "until_budget": False},
        ),
    )
    status = service.status(run)
    assert status.state == "cancelled" and "cancelled" in status.error
    result = service.result(run)
    assert result.layout is not None and result.checkpoints
    resumed = LocalService(tmp_path).resume(
        result.checkpoints[-1], Request(solver="inorder", units=800)
    )
    after = service.status(resumed)
    assert after.state == "done" and service.result(resumed).assessment.valid
    assert (
        service.status(resumed).run == resumed
        and RunRequest(resumed, tmp_path).parent == run
    )


def RunRequest(run: str, root: Path):
    from kohakulayout.service import (
        RunDir,
    )  # justify: a test-local helper, kept beside its single use

    return RunDir(root, run).request()


def test_failed_request_is_reported_not_raised(tmp_path: Path) -> None:
    service = LocalService(tmp_path)
    run = service.submit(toy(), Request(solver="nowhere"))
    status = service.status(run)
    assert status.state == "failed" and "no solver" in status.error
    assert service.result(run).layout is None
