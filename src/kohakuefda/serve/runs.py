"""Runs: one scenario, four stages with checkpoints, recorded frames, and an event log.

A run lives in memory and, when the manager has a workspace, under ``runs/<id>/`` as
``run.json``, ``scenario.toml``, one JSON file per checkpoint and ``frames/<stage>.json``.
Stages execute on worker threads; starting a stage clears every later stage; every state
change and every frame is appended to the run's event log, which the event stream tails.
"""

import json
import logging
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from kohakuefda.flow.evaluate import Evaluation
from kohakuefda.layout.stages import (
    STAGES,
    layout_stage,
    netlist_stage,
    params_of,
    plan_stage,
    verify_stage,
)
from kohakuefda.model.base import EfdaModel
from kohakuefda.model.cells import Netlist
from kohakuefda.model.control import CancelledError
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.layout import Layout
from kohakuefda.model.placement import Placement
from kohakuefda.model.plan import Plan
from kohakuefda.model.scenario import Scenario
from kohakuefda.verify.report import Report

ARTIFACT_MODELS: dict[str, type[EfdaModel]] = {
    "plan": Plan,
    "netlist": Netlist,
    "placement": Placement,
    "layout": Layout,
    "evaluation": Evaluation,
    "report": Report,
}
PRODUCES = {
    "plan": ("plan",),
    "netlist": ("netlist",),
    "layout": ("placement", "layout"),
    "verify": ("report", "evaluation"),
}
FRAME_STAGES = ("layout",)
FINAL = ("done", "incomplete", "failed", "cancelled", "idle")

log = logging.getLogger(__name__)


class RunError(ValueError):
    """A request the run manager refuses; the message goes to the client."""


class StageState:
    """Status, parameters, timing and error of one stage of a run."""

    def __init__(self) -> None:
        self.status = "idle"
        self.params: dict = {}
        self.started: float | None = None
        self.finished: float | None = None
        self.error = ""
        self.outcome: dict | None = None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "params": self.params,
            "started": self.started,
            "finished": self.finished,
            "error": self.error,
            "outcome": self.outcome,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "StageState":
        state = cls()
        state.status = raw.get("status", "idle")
        if state.status in ("queued", "running"):
            state.status = "idle"
        state.params = raw.get("params", {})
        state.started = raw.get("started")
        state.finished = raw.get("finished")
        state.error = raw.get("error", "")
        state.outcome = raw.get("outcome")
        return state


class Run:
    """One scenario with its stage states, checkpoints, frames and event log."""

    def __init__(self, run_id: str, scenario: Scenario, directory: Path | None) -> None:
        self.id = run_id
        self.scenario = scenario
        self.directory = directory
        self.created = time.time()
        self.stages = {stage: StageState() for stage in STAGES}
        self.artifacts: dict[str, EfdaModel] = {}
        self.frames: dict[str, list[dict]] = {stage: [] for stage in FRAME_STAGES}
        self.events: list[dict] = []
        self.condition = threading.Condition()
        self.cancel = threading.Event()

    def summary(self) -> dict:
        return {
            "id": self.id,
            "created": self.created,
            "scenario": self.scenario.model_dump(mode="json"),
            "stages": {stage: state.to_dict() for stage, state in self.stages.items()},
            "artifacts": sorted(self.artifacts),
            "frames": {stage: len(frames) for stage, frames in self.frames.items()},
            "busy": self.busy,
            "events": len(self.events),
        }

    @property
    def busy(self) -> bool:
        return any(s.status in ("queued", "running") for s in self.stages.values())

    def emit(self, kind: str, stage: str, data: dict, index: int | None = None) -> None:
        """Append an event; ``index`` is the frame's position in its stage's frame list."""
        with self.condition:
            event = {
                "seq": len(self.events) + 1,
                "time": time.time(),
                "kind": kind,
                "stage": stage,
                "data": data,
            }
            if index is not None:
                event["index"] = index
            self.events.append(event)
            self.condition.notify_all()

    def events_since(self, seq: int, timeout: float | None = None) -> list[dict]:
        """Events with a sequence number above ``seq``; waits up to ``timeout`` for new ones."""
        with self.condition:
            if timeout is not None and len(self.events) <= seq:
                self.condition.wait(timeout)
            return self.events[seq:]

    def write_meta(self) -> None:
        if self.directory is None:
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        meta = {
            "id": self.id,
            "created": self.created,
            "stages": {stage: state.to_dict() for stage, state in self.stages.items()},
        }
        (self.directory / "run.json").write_text(
            json.dumps(meta, indent=1) + "\n", encoding="utf-8"
        )
        (self.directory / "scenario.toml").write_text(
            self.scenario.to_toml(), encoding="utf-8"
        )

    def write_stage(self, stage: str) -> None:
        if self.directory is None:
            return
        for name in PRODUCES[stage]:
            path = self.directory / f"{name}.json"
            artifact = self.artifacts.get(name)
            if artifact is None:
                path.unlink(missing_ok=True)
            else:
                path.write_text(
                    artifact.model_dump_json(indent=1) + "\n", encoding="utf-8"
                )
        if stage in FRAME_STAGES:
            path = self.directory / "frames" / f"{stage}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self.frames[stage]), encoding="utf-8")
        self.write_meta()

    @classmethod
    def read(cls, directory: Path) -> "Run":
        """A run restored from its directory; unfinished stages come back idle."""
        meta = json.loads((directory / "run.json").read_text(encoding="utf-8"))
        scenario = Scenario.from_toml(directory / "scenario.toml")
        run = cls(meta["id"], scenario, directory)
        run.created = meta.get("created", run.created)
        for stage, raw in meta.get("stages", {}).items():
            if stage in run.stages:
                run.stages[stage] = StageState.from_dict(raw)
        for name, model in ARTIFACT_MODELS.items():
            path = directory / f"{name}.json"
            if path.is_file():
                run.artifacts[name] = model.model_validate(
                    json.loads(path.read_text(encoding="utf-8"))
                )
        for stage in FRAME_STAGES:
            path = directory / "frames" / f"{stage}.json"
            if path.is_file():
                run.frames[stage] = json.loads(path.read_text(encoding="utf-8"))
        state = run.stages["layout"]
        if state.status == "done" and state.outcome is None:
            final = next(
                (f for f in reversed(run.frames["layout"]) if f.get("kind") == "final"),
                None,
            )
            if final is not None and "status" in final:
                state.outcome = final.get("outcome") or {
                    "status": final["status"],
                    "routed": final.get("evidence", {}).get(
                        "routed", final.get("clean", False)
                    ),
                    "placed": final.get("placed"),
                    "total": final.get("total"),
                    "elapsed": final.get("elapsed"),
                    "settings": {"runtime": state.params},
                }
                if state.outcome["routed"] is False:
                    state.status = "incomplete"
        return run


class RunManager:
    """Creates runs, executes their stages on worker threads, restores runs from a workspace."""

    def __init__(
        self, dataset: Dataset, workspace: Path | None = None, workers: int = 1
    ) -> None:
        self.dataset = dataset
        self.workspace = workspace
        self.executor = ThreadPoolExecutor(max_workers=max(1, workers))
        self.lock = threading.Lock()
        self._runs: dict[str, Run] = {}
        if workspace is not None:
            self._restore(workspace / "runs")

    def _restore(self, root: Path) -> None:
        if not root.is_dir():
            return
        for directory in sorted(root.iterdir()):
            if (directory / "run.json").is_file():
                try:
                    run = Run.read(directory)
                except (OSError, ValueError, KeyError):
                    continue
                self._runs[run.id] = run

    def create(self, scenario: Scenario) -> Run:
        run_id = uuid.uuid4().hex[:8]
        directory = self.workspace / "runs" / run_id if self.workspace else None
        run = Run(run_id, scenario, directory)
        run.write_meta()
        with self.lock:
            self._runs[run_id] = run
        log.debug("run %s created under %s", run_id, directory or "memory")
        return run

    def get(self, run_id: str) -> Run | None:
        with self.lock:
            return self._runs.get(run_id)

    def runs(self) -> list[Run]:
        with self.lock:
            return sorted(self._runs.values(), key=lambda r: r.created, reverse=True)

    def require(self, run_id: str) -> Run:
        run = self.get(run_id)
        if run is None:
            raise RunError(f"no run {run_id!r}")
        return run

    def start(
        self,
        run_id: str,
        stage: str,
        params: dict | None = None,
        through: str | None = None,
    ) -> list[str]:
        """Queue ``stage`` (and every stage up to ``through``); later stages are cleared."""
        run = self.require(run_id)
        if stage not in STAGES:
            raise RunError(f"unknown stage {stage!r}")
        last = through or stage
        if last not in STAGES or STAGES.index(last) < STAGES.index(stage):
            raise RunError(f"cannot run {stage} through {last}")
        if run.busy:
            raise RunError("the run is busy; cancel it first")
        first = STAGES.index(stage)
        for earlier in STAGES[:first]:
            if run.stages[earlier].status != "done":
                raise RunError(f"stage {earlier} must be done before {stage}")
        queued = list(STAGES[first : STAGES.index(last) + 1])
        settings = {
            name: params_of(name, params if name == stage else None) for name in queued
        }
        run.cancel.clear()
        for name in STAGES[first:]:
            state = run.stages[name]
            state.status = "idle"
            state.error = ""
            state.outcome = None
            state.started = state.finished = None
            for artifact in PRODUCES[name]:
                run.artifacts.pop(artifact, None)
            if name in FRAME_STAGES:
                run.frames[name] = []
            run.emit("stage", name, state.to_dict())
        for name in queued:
            run.stages[name].status = "queued"
            run.stages[name].params = settings[name]
            run.emit("stage", name, run.stages[name].to_dict())
        run.write_meta()
        log.info("run %s: queued %s", run.id, queued)
        self.executor.submit(self._execute, run, queued)
        return queued

    def cancel(self, run_id: str) -> None:
        log.info("run %s: cancel requested", run_id)
        self.require(run_id).cancel.set()

    def delete(self, run_id: str) -> None:
        """Cancel the run, forget it and remove its directory."""
        run = self.require(run_id)
        run.cancel.set()
        with self.lock:
            self._runs.pop(run_id, None)
        if run.directory is not None:
            shutil.rmtree(run.directory, ignore_errors=True)
        log.debug("run %s removed", run_id)

    def _execute(self, run: Run, stages: list[str]) -> None:
        for stage in stages:
            state = run.stages[stage]
            if run.cancel.is_set():
                state.status = "cancelled"
                run.emit("stage", stage, state.to_dict())
                log.info("run %s: stage %s cancelled before it started", run.id, stage)
                continue
            state.status = "running"
            state.started = time.time()
            run.emit("stage", stage, state.to_dict())
            log.info("run %s: stage %s started", run.id, stage)
            try:
                self._run_stage(run, stage, state.params)
                state.status = (
                    "incomplete"
                    if state.outcome and not state.outcome["routed"]
                    else "done"
                )
            except CancelledError:
                state.status = "cancelled"
            except Exception as error:  # noqa: BLE001
                if state.outcome and state.outcome.get("status") in (
                    "no_solution_found",
                    "budget_exhausted",
                ):
                    state.status = "incomplete"
                else:
                    state.status = "failed"
                    state.error = f"{type(error).__name__}: {error}"
            state.finished = time.time()
            duration = state.finished - state.started
            if state.status == "failed":
                log.warning(
                    "run %s: stage %s failed in %.1fs: %s",
                    run.id,
                    stage,
                    duration,
                    state.error,
                )
            else:
                log.info(
                    "run %s: stage %s %s in %.1fs",
                    run.id,
                    stage,
                    state.status,
                    duration,
                )
            if state.status != "done":
                for later in stages[stages.index(stage) + 1 :]:
                    run.stages[later].status = "idle"
            run.write_stage(stage)
            run.emit("stage", stage, state.to_dict())
            if state.status != "done":
                for later in stages[stages.index(stage) + 1 :]:
                    run.emit("stage", later, run.stages[later].to_dict())
                return

    def _run_stage(self, run: Run, stage: str, params: dict) -> None:
        dataset = self.dataset
        artifacts = run.artifacts

        def observe(frame: dict) -> None:
            if frame.get("kind") == "final" and frame.get("outcome"):
                run.stages[stage].outcome = frame["outcome"]
            run.frames[stage].append(frame)
            run.emit("frame", stage, frame, len(run.frames[stage]) - 1)

        if stage == "plan":
            artifacts["plan"] = plan_stage(dataset, run.scenario)
        elif stage == "netlist":
            artifacts["netlist"] = netlist_stage(
                dataset, run.scenario, artifacts["plan"]
            )
            errors = artifacts["netlist"].errors
            if errors or artifacts["plan"].status == "infeasible":
                for finding in errors:
                    log.error(
                        finding.message, rule=finding.rule, subject=finding.subject
                    )
                raise RunError(
                    "; ".join(f.message for f in errors)
                    or "the plan is infeasible: nothing can make what was asked for"
                )
        elif stage == "layout":
            artifacts["placement"], artifacts["layout"] = layout_stage(
                dataset, artifacts["netlist"], params, observe, run.cancel.is_set
            )
        elif stage == "verify":
            report, evaluation = verify_stage(
                dataset,
                artifacts["plan"],
                artifacts["netlist"],
                artifacts.get("placement"),
                artifacts.get("layout"),
            )
            artifacts["report"] = report
            if evaluation is not None:
                artifacts["evaluation"] = evaluation

    def shutdown(self) -> None:
        for run in self.runs():
            run.cancel.set()
        self.executor.shutdown(wait=False, cancel_futures=True)
