"""Solver-facing queries, atomic actions and assessed incumbent publication."""

import json
import logging
import random
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from kohakuefda.framework.actions import default_actions
from kohakuefda.framework.assessment import AreaWire
from kohakuefda.framework.backend import SiteBackend
from kohakuefda.framework.control import FrameworkError, Rejected
from kohakuefda.framework.execution import gather
from kohakuefda.framework.problem import digest
from kohakuefda.model.solver import (
    Action,
    AttemptResult,
    Candidate,
    Scope,
    Screen,
    Snapshot,
    SolveEvent,
)

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class BuildMark:
    owner: str
    key: int


class EditWorkspace:
    """Scoped scratch operations supplied to action handlers."""

    def __init__(self, context: "Context", scope: Scope) -> None:
        self._context = context
        self._scope = scope
        self._active = True

    def check(self) -> None:
        if not self._active:
            raise FrameworkError("workspace is closed")
        self._context.budget.check()

    @property
    def view(self):
        self.check()
        return self._context.view

    def _machine(self, block_id: str) -> None:
        self.check()
        if block_id not in self._scope.machines:
            raise Rejected(f"machine {block_id} is outside scope", "scope_required")

    def put(self, block_id: str, anchor: tuple) -> None:
        self._machine(block_id)
        self._context._backend.put(block_id, anchor)

    def remove(self, block_id: str) -> None:
        self._machine(block_id)
        self._context._backend.remove(block_id)

    def reroute(self, routes: tuple[str, ...]) -> None:
        self.check()
        if self._scope.routes is not None and set(routes) - self._scope.routes:
            raise Rejected("routes outside scope", "scope_required")
        self._context._backend.reroute(routes)


class Builder:
    """Partial construction with routed ready connections; never an improvement state."""

    def __init__(self, context: "Context") -> None:
        self.context = context
        self._marks = {}
        self._counter = 0
        self._closed = False

    def check(self) -> None:
        if self._closed or self.context.current is not None:
            raise FrameworkError("builder is closed")
        self.context.budget.check()

    def reset(self) -> None:
        self.check()
        self.context._backend.clear()
        self.context.revision += 1

    def mark(self) -> BuildMark:
        self.check()
        self._counter += 1
        self._marks[self._counter] = self.context._backend.mark()
        return BuildMark(self.context.session, self._counter)

    def restore(self, mark: BuildMark) -> None:
        self.check()
        if mark.owner != self.context.session or mark.key not in self._marks:
            raise FrameworkError("foreign build mark")
        self.context._backend.restore(self._marks[mark.key])
        self.context.revision += 1

    def release(self, mark: BuildMark) -> None:
        if mark.owner == self.context.session:
            self._marks.pop(mark.key, None)

    def place(self, block_id: str, anchor: tuple) -> AttemptResult:
        self.check()
        ctx = self.context
        ctx.budget.charge("actions")
        try:
            ctx._backend.put(block_id, anchor)
        except Rejected as error:
            return AttemptResult(error.status, message=str(error))
        ctx.revision += 1
        return AttemptResult("placed")

    def finish(self) -> Snapshot:
        self.check()
        snapshot = self.context._backend.capture()
        if not snapshot.assessment.routed:
            raise Rejected(
                "construction is not a complete geometry-checked routed state"
            )
        self._closed = True
        self._marks.clear()
        self.context._current = snapshot
        self.context._builder = None
        self.context.consider(snapshot)
        return snapshot

    def diagnostic(self) -> Snapshot:
        self.check()
        return self.context._backend.capture()


class Context:
    """Public strategy surface; live geometry is owned by its backend."""

    def __init__(
        self,
        backend: SiteBackend,
        seed: int = 0,
        objective=None,
        actions: dict | None = None,
        observe: Callable[[SolveEvent], None] | None = None,
    ) -> None:
        self._backend = backend
        self.problem = backend.problem
        self.budget = backend.budget
        self.blocks = backend.blocks
        self.links = backend.links
        self.seed = seed
        self.objective = objective or AreaWire()
        self.actions = {**default_actions(), **(actions or {})}
        self.observe = observe
        self.session = uuid.uuid4().hex
        self.revision = 0
        self._current = None
        self.best_routed = None
        self.best_verified = None
        self.diagnostic = None
        self._builder = None
        self._issued = {}
        self._sequence = 0
        self._streams = {}
        self.workers = 1

    @property
    def repeatable_edits(self) -> bool:
        return self._backend.repeatable_edits and self.actions == default_actions()

    @property
    def current(self) -> Snapshot | None:
        return self._current

    @property
    def world_settings(self) -> dict:
        return dict(self._backend.settings)

    def gather(self, function, jobs: tuple[tuple, ...]) -> list:
        return gather(function, jobs, self.workers, self.budget, self.emit)

    @property
    def view(self):
        return self._backend.view(self.revision)

    @property
    def anchors(self) -> tuple:
        return tuple(self._backend.site.placed.items())

    @property
    def area(self) -> tuple:
        return self._backend.site.area

    @property
    def pylon_width(self):
        return self._backend.pylon_width

    def slot_anchors(self, block_id: str) -> tuple:
        return self._backend.slot_anchors(block_id)

    def border_anchors(self) -> tuple:
        return self._backend.border_anchors()

    def group_anchors(self, block_id: str) -> tuple:
        return self._backend.group_anchors(block_id)

    def rng(self, namespace: str = "solver") -> random.Random:
        if namespace not in self._streams:
            self._streams[namespace] = random.Random(
                int(digest(str(self.seed), namespace), 16)
            )
        return self._streams[namespace]

    def builder(self) -> Builder:
        if self._current is not None:
            raise FrameworkError("cannot construct over a published state")
        if self._builder is None:
            self._builder = Builder(self)
        return self._builder

    def emit(
        self, kind: str, payload: dict | None = None, duration: float = 0.0
    ) -> None:
        self._sequence += 1
        if self.observe is not None:
            event = SolveEvent(
                self._sequence,
                kind,
                self.budget.elapsed,
                duration,
                self.revision,
                json.dumps(payload or {}),
            )
            try:
                self.observe(event)
            except Exception:
                log.exception("solver observer failed")

    def frame(self, kind: str, **fields) -> None:
        if self.observe is not None:
            self.emit(kind, {**self._backend.frame(kind), **fields})

    def attempt(
        self,
        action: Action,
        base_revision: int | None = None,
        *,
        screen: Screen | None = None,
    ) -> AttemptResult:
        """Try an action without changing current; publication requires accept()."""
        self.budget.charge("actions")
        if self._current is None or not self._current.assessment.routed:
            raise FrameworkError("improvement needs a complete routed base")
        if base_revision is not None and base_revision != self.revision:
            return AttemptResult("stale", message="base revision changed")
        if action.name not in self.actions:
            return AttemptResult("unsupported", message=f"unknown action {action.name}")
        scope = action.scope or Scope(frozenset(i for i, _ in action.anchors))
        mark = self._backend.mark()
        before = self._backend.route_state()
        anchors = dict(self.view.anchors)
        workspace = EditWorkspace(self, scope)
        started = time.monotonic()
        result = None
        try:
            self.actions[action.name](workspace, action)
            self.budget.check()
            after = self.view
            if after.missing or after.unrouted:
                raise Rejected("action left required machines or routes missing")
            changed = {i for i, a in after.anchors if anchors.get(i) != a}
            if changed - scope.machines:
                raise Rejected(
                    "action changed machines outside scope", "scope_required"
                )
            route_changes = {
                i for i, s in self._backend.route_state().items() if before[i] != s
            }
            if scope.routes is not None and route_changes - scope.routes:
                result = AttemptResult(
                    "scope_required",
                    required_routes=tuple(sorted(route_changes - scope.routes)),
                )
            else:
                snapshot = self._backend.capture(screen=screen)
                self.budget.check()
                if (
                    not scope.support
                    and json.loads(snapshot.placement_json)["pylons"]
                    != json.loads(self._current.placement_json)["pylons"]
                ):
                    raise Rejected(
                        "support placement changed outside scope", "scope_required"
                    )
                if not snapshot.assessment.routed:
                    raise Rejected(
                        "candidate failed geometric assessment", "hard_conflict"
                    )
                candidate = Candidate(self.session, self.revision, snapshot)
                self._issued[id(candidate)] = (candidate, self._backend.mark())
                result = AttemptResult("candidate", candidate)
        except Rejected as error:
            result = AttemptResult(error.status, message=str(error))
        finally:
            workspace._active = False
            self._backend.restore(mark)
        self.emit(
            "attempt",
            {"action": action.name, "outcome": result.status},
            time.monotonic() - started,
        )
        return result

    def accept(self, candidate: Candidate) -> None:
        self.budget.check()
        record = self._issued.pop(id(candidate), None)
        if (
            record is None
            or record[0] is not candidate
            or candidate.session != self.session
        ):
            raise FrameworkError("candidate was not issued by this context")
        if candidate.base_revision != self.revision:
            raise FrameworkError("stale candidate")
        self._backend.restore(record[1])
        self._current = candidate.snapshot
        self.revision += 1
        self.consider(self._current)
        self.emit(
            "accepted",
            {
                "state_id": self._current.id,
                "metrics": dict(self._current.assessment.metrics),
            },
        )

    def discard(self, candidate: Candidate) -> None:
        self._issued.pop(id(candidate), None)

    def consider(self, snapshot: Snapshot) -> None:
        if snapshot is not self._current and not any(
            record[0].snapshot is snapshot for record in self._issued.values()
        ):
            raise FrameworkError(
                "only snapshots assessed by this context may be archived"
            )
        for name, eligible in (
            ("best_routed", snapshot.assessment.routed),
            ("best_verified", snapshot.assessment.verified),
        ):
            best = getattr(self, name)
            if eligible and (
                best is None
                or self.objective.key(snapshot.assessment)
                < self.objective.key(best.assessment)
            ):
                setattr(self, name, snapshot)

    def import_snapshot(self, snapshot: Snapshot) -> None:
        """Load and re-assess a portable snapshot, never trusting its supplied evidence."""
        self.budget.check()
        mark = self._backend.mark()
        try:
            self._backend.load(snapshot)
            checked = self._backend.capture()
            if (
                checked.layout_json != snapshot.layout_json
                or not checked.assessment.routed
            ):
                raise FrameworkError("snapshot failed reconstruction/assessment")
        except BaseException:
            self._backend.restore(mark)
            raise
        self._current = checked
        self.revision += 1
        self.consider(checked)

    def verify(self) -> Snapshot | None:
        """Assess current production rates; no plan means not_checked, not success."""
        if self._current is not None:
            self._current = self._backend.capture(rates=True)
            self.consider(self._current)
        return self._current
