"""Run directories: every artifact of a run on disk, self-describing, the source of truth for status."""

import json
from pathlib import Path

from kohakulayout.engine.checkpoint import Checkpoint
from kohakulayout.ir import Assessment, Layout, Problem
from kohakulayout.service.protocol import Request, RunStatus


class RunDir:
    def __init__(self, root: Path, run: str) -> None:
        self.root = Path(root)
        self.run = run
        self.path = self.root / "runs" / run

    # ------------------------------------------------------------- paths
    @property
    def problem_path(self) -> Path:
        return self.path / "problem.json"

    @property
    def request_path(self) -> Path:
        return self.path / "request.json"

    @property
    def status_path(self) -> Path:
        return self.path / "status.json"

    @property
    def best_layout_path(self) -> Path:
        return self.path / "best.layout.json"

    @property
    def best_assessment_path(self) -> Path:
        return self.path / "best.assessment.json"

    @property
    def checkpoints_path(self) -> Path:
        return self.path / "checkpoints"

    @property
    def events_path(self) -> Path:
        return self.path / "events.jsonl"

    @property
    def cancel_path(self) -> Path:
        return self.path / "cancel"

    # ------------------------------------------------------------ writes
    def create(self, problem: Problem, request: Request) -> None:
        self.path.mkdir(parents=True, exist_ok=False)
        self.problem_path.write_text(problem.to_json())
        self.request_path.write_text(request.model_dump_json(indent=2))
        self.write_status(RunStatus(run=self.run, state="queued"))

    def write_status(self, status: RunStatus) -> None:
        tmp = self.status_path.with_suffix(".json.tmp")
        tmp.write_text(status.model_dump_json(indent=2))
        tmp.replace(self.status_path)

    def write_best(self, layout: Layout, assessment: Assessment) -> None:
        self.best_layout_path.write_text(layout.to_json())
        self.best_assessment_path.write_text(assessment.to_json())

    def write_checkpoint(self, checkpoint: Checkpoint) -> Path:
        self.checkpoints_path.mkdir(parents=True, exist_ok=True)
        target = self.checkpoints_path / f"{checkpoint.seq:06d}.json"
        target.write_text(checkpoint.to_json())
        return target

    def request_cancel(self) -> None:
        self.cancel_path.write_text("cancel\n")

    # ------------------------------------------------------------- reads
    def exists(self) -> bool:
        return self.status_path.exists()

    def problem(self) -> Problem:
        return Problem.from_json(self.problem_path.read_text())

    def request(self) -> Request:
        return Request.model_validate(json.loads(self.request_path.read_text()))

    def status(self) -> RunStatus:
        return RunStatus.model_validate(json.loads(self.status_path.read_text()))

    def best(self) -> tuple[Layout, Assessment] | None:
        if not self.best_layout_path.exists():
            return None
        return Layout.from_json(
            self.best_layout_path.read_text()
        ), Assessment.from_json(self.best_assessment_path.read_text())

    def checkpoints(self) -> tuple[Checkpoint, ...]:
        if not self.checkpoints_path.exists():
            return ()
        return tuple(
            Checkpoint.from_json(p.read_text())
            for p in sorted(self.checkpoints_path.glob("*.json"))
        )

    def cancelled(self) -> bool:
        return self.cancel_path.exists()


def new_run_id(root: Path, problem: Problem, request: Request) -> str:
    """``<digest8>-<solver>-<seed>-<n>``, unique under ``root``."""
    base = f"{problem.digest()[:8]}-{request.solver}-{request.seed}"
    runs = Path(root) / "runs"
    n = 0
    while (runs / f"{base}-{n}").exists():
        n += 1
    return f"{base}-{n}"


def list_runs(root: Path) -> tuple[RunStatus, ...]:
    runs = Path(root) / "runs"
    if not runs.exists():
        return ()
    out = []
    for path in sorted(runs.iterdir()):
        run = RunDir(root, path.name)
        if run.exists():
            out.append(run.status())
    return tuple(out)


__all__ = ["RunDir", "list_runs", "new_run_id"]
