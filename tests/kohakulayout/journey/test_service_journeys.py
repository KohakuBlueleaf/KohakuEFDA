"""Journeys through the service: submit, watch, cancel, resume, result; local and process agree."""

import time
from pathlib import Path

import pytest

from kohakulayout.service import EventFilter, LocalService, ProcessService, Request
from kohakulayout.templates.physics.gates import from_expressions, problem

pytestmark = pytest.mark.journey


def toy():
    return problem(from_expressions(["s = a ^ b", "c = a & b"]), width=32, height=16)


class TestServiceJourneys:
    def test_local_submit_watch_result(self, tmp_path: Path) -> None:
        service = LocalService(tmp_path)
        run = service.submit(
            toy(),
            Request(
                solver="baseline", seed=4, units=3000, params={"shrink_rounds": 10}
            ),
        )
        assert service.wait(run).state == "done"
        frames = [
            e
            for e in service.events(
                run, EventFilter(kinds=frozenset({"frame"}), every=3)
            )
        ]
        assert frames and frames[0].payload.phase == "start"
        result = service.result(run)
        assert (
            result.assessment.valid
            and result.layout.check_against(toy().netlist, toy().fabric) == []
        )

    def test_process_submit_watch_cancel_resume_result(self, tmp_path: Path) -> None:
        service = ProcessService(tmp_path)
        try:
            run = service.submit(
                toy(),
                Request(
                    solver="anneal",
                    seed=5,
                    seconds=60,
                    params={"improvement_steps": 100000},
                ),
            )
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                if any(e.kind == "assessment" for e in service.events(run)):
                    break
                time.sleep(0.05)
            service.cancel(run)
            status = service.wait(run, timeout=60)
            assert status.state == "cancelled", status
            result = service.result(run)
            assert result.layout is not None and result.checkpoints
            resumed = service.resume(
                result.checkpoints[-1], Request(solver="inorder", units=2000)
            )
            assert service.wait(resumed, timeout=120).state == "done"
            assert service.result(resumed).assessment.valid
            assert [e.kind for e in service.events(resumed)][-1] == "status"
        finally:
            service.close()

    def test_local_and_process_agree(self, tmp_path: Path) -> None:
        request = Request(solver="inorder", seed=9, units=2000)
        local = LocalService(tmp_path / "local").submit(toy(), request)
        process = ProcessService(tmp_path / "process")
        try:
            remote = process.submit(toy(), request)
            assert process.wait(remote, timeout=120).state == "done"
            assert (
                process.result(remote).layout.digest()
                == LocalService(tmp_path / "local").result(local).layout.digest()
            )
        finally:
            process.close()
