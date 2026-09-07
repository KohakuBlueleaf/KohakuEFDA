"""Isolated boundary-relaxed sessions with shared budgets and strict target publication."""

import json
from dataclasses import replace
from types import MappingProxyType

from kohakuefda.framework.backend import SiteBackend
from kohakuefda.framework.context import Context
from kohakuefda.framework.control import (
    ConfigurationError,
    FrameworkError,
    LocalBudgetExhausted,
    Rejected,
)
from kohakuefda.framework.problem import digest
from kohakuefda.layout.board import Board
from kohakuefda.layout.geometry import machine_footprint, unit_footprint
from kohakuefda.model.layout import Layout
from kohakuefda.model.solver import Issue
from kohakuefda.verify.rules.geometry import ring_allowed


class BoundaryObjective:
    """Target overflow distance first, then workspace occupied area and wire length."""

    name = "target-overflow-v1"

    def key(self, assessment):
        return self.key_metrics(dict(assessment.metrics))

    def key_metrics(self, metrics):
        return (metrics["target_overflow"], metrics["area"], metrics["wire_path_cells"])


def outside_distance(cell, area):
    x, y = cell
    x0, y0, x1, y1 = area
    return max(x0 - x, 0, x - x1 + 1) + max(y0 - y, 0, y - y1 + 1)


def boundary_metrics(dataset, layout, target):
    """Measure real target violations without charging allowed outside-ring pipes."""
    grid = (0, 0, *target.grid)
    required = set()
    external = set()
    for placed in layout.machines:
        cells = set(machine_footprint(dataset, placed))
        (external if ring_allowed(placed.machine_id) else required).update(cells)
    for unit in layout.units:
        required.update(unit_footprint(dataset, unit))
    for segment in layout.segments:
        (required if segment.kind == "belt" else external).update(segment.cells)
    required.update(e.cell for e in layout.entries)
    distances = [outside_distance(c, target.area) for c in required]
    distances += [outside_distance(c, grid) for c in external]
    return {
        "target_overflow": float(sum(distances)),
        "target_outside_cells": float(sum(d > 0 for d in distances)),
        "target_max_distance": float(max(distances, default=0)),
        "target_width": float(target.square[0]),
        "target_height": float(target.square[1]),
    }


class WorkspaceBackend(SiteBackend):
    """A distinct snapshot domain; only the workspace extent is relaxed."""

    def __init__(self, parent, extra):
        original = parent._backend
        self.target = original.site.board
        square = tuple(size + extra for size in self.target.square)
        self.name = f"site-workspace-{square[0]}x{square[1]}-v1"
        board = Board(
            square,
            self.target.ring,
            list(self.target.slots),
            set(self.target.fixed),
            list(self.target.findings),
            self.target.area,
        )
        super().__init__(
            parent.problem,
            parent.budget,
            parent.world_settings,
            original.actual_backend,
            original.routing,
            original.coverage,
            board,
        )

    def capture(self, rates=False, screen=None):
        snapshot = super().capture(rates)
        layout = Layout.model_validate_json(snapshot.layout_json)
        metrics = {
            **dict(snapshot.assessment.metrics),
            **boundary_metrics(self.site.dataset, layout, self.target),
        }
        if screen is not None and not screen(MappingProxyType(metrics)):
            raise Rejected("solver screened workspace metrics", "screened")
        return replace(
            snapshot,
            assessment=replace(snapshot.assessment, metrics=tuple(metrics.items())),
        )


class Workspace:
    """Own an oversized search context; publish only reassessed target-valid layouts."""

    def __init__(self, parent, extra: int, projection_actions: int = 12000):
        if type(extra) is not int or not 0 < extra <= 256:
            raise ConfigurationError("workspace extra must be an integer in [1, 256]")
        if parent.current is not None or isinstance(parent._backend, WorkspaceBackend):
            raise FrameworkError("workspace requires an uncommitted target context")
        parent.budget.check()
        self.parent = parent
        self.backend = WorkspaceBackend(parent, extra)
        self.context = Context(
            self.backend, parent.seed, BoundaryObjective(), observe=self.observe
        )
        self.best = None
        self.first_routed = None
        self.projection_actions = projection_actions
        self.last_projection = None
        parent.emit(
            "workspace_opened",
            {
                "target": self.backend.target.area,
                "area": self.context.area,
                "extra": extra,
            },
        )

    def observe(self, event):
        ctx = self.context
        snapshot = ctx.best_routed or ctx.diagnostic
        if snapshot is not None and snapshot.id != (
            self.best.id if self.best else None
        ):
            self.retain(snapshot)
        if event.kind in ("transition", "constructed", "accepted"):
            self.parent.emit(
                "workspace_search",
                {
                    "event": event.kind,
                    "area": ctx.area,
                    "detail": json.loads(event.payload_json),
                },
            )

    def retain(self, snapshot):
        self.best = snapshot
        if snapshot.assessment.routed and self.first_routed is None:
            self.first_routed = self.parent.budget.elapsed
            self.parent.emit(
                "workspace_constructed",
                {
                    "elapsed": self.first_routed,
                    "area": self.context.area,
                    "metrics": dict(snapshot.assessment.metrics),
                },
            )
        issue = Issue(
            "layout.workspace_only",
            "error",
            "layout",
            "temporary workspace realization; not validated for the requested basement",
        )
        metrics = {
            **dict(snapshot.assessment.metrics),
            "workspace_routed": float(snapshot.assessment.routed),
            "workspace_width": float(self.backend.site.board.square[0]),
            "workspace_height": float(self.backend.site.board.square[1]),
        }
        assessment = replace(
            snapshot.assessment,
            geometry="fail",
            rates="not_checked",
            issues=(*snapshot.assessment.issues, issue),
            metrics=tuple(metrics.items()),
        )
        self.parent.diagnostic = replace(snapshot, assessment=assessment)
        self.parent.emit(
            "workspace_best",
            {
                "snapshot": snapshot.id,
                "workspace_routed": snapshot.assessment.routed,
                "target_routed": False,
                "metrics": metrics,
            },
        )
        if snapshot.assessment.routed and self.parent.current is None:
            if metrics["target_overflow"] == 0:
                self.publish(snapshot)
            else:
                self.project(snapshot)

    def project(self, snapshot):
        """Try coupled reconstruction on the real board when all machine anchors fit."""
        parent = self.parent
        raw = json.loads(snapshot.payload)
        anchors = tuple((i, tuple(a)) for i, a in raw["anchors"])
        if anchors == self.last_projection or len(anchors) != len(parent.blocks):
            return False
        target = self.backend.target.area
        for i, (x, y, r) in anchors:
            if any(
                outside_distance((x + dx, y + dy), target)
                for dx, dy in parent.blocks[i].footprints[r // 90]
            ):
                return False
        self.last_projection = anchors
        builder = parent.builder()
        try:
            with (
                parent.budget.limit(actions=self.projection_actions),
                builder.transaction() as trial,
            ):
                builder.reset()
                for i, anchor in anchors:
                    if builder.place(i, anchor).status != "placed":
                        return False
                trial.assess()
                trial.accept()
            builder.finish()
            return True
        except (Rejected, LocalBudgetExhausted):
            return False

    def publish(self, snapshot) -> bool:
        """Reconstruct and fully reassess on the original board before target publication."""
        if (
            snapshot.backend != self.backend.name
            or snapshot.problem_id != self.parent.problem.id
        ):
            raise ConfigurationError("foreign workspace snapshot")
        layout = Layout.model_validate_json(snapshot.layout_json)
        if (
            not snapshot.assessment.routed
            or boundary_metrics(self.backend.site.dataset, layout, self.backend.target)[
                "target_overflow"
            ]
        ):
            return False
        parent = self.parent
        backend = parent._backend
        mark = backend.mark()
        try:
            raw = json.loads(snapshot.payload)
            width, height = self.backend.target.grid
            raw["history"] = [
                [
                    (cell, value)
                    for cell, value in layer
                    if 0 <= cell[0] < width and 0 <= cell[1] < height
                ]
                for layer in raw["history"]
            ]
            payload = json.dumps(raw, separators=(",", ":"))
            transferred = replace(
                snapshot,
                backend=backend.name,
                payload=payload,
                id=digest(snapshot.problem_id, payload, snapshot.layout_json),
            )
            backend.load(transferred)
            checked = backend.capture()
            parent.budget.check()
            if not checked.assessment.routed:
                return False
        finally:
            backend.restore(mark)
        parent.import_snapshot(checked)
        parent.emit(
            "constructed", {"state_id": parent.current.id, "from_workspace": True}
        )
        return True

    def transfer(self, snapshot):
        """Reassess a smaller workspace's physical realization in this larger workspace."""
        if (
            snapshot.problem_id != self.parent.problem.id
            or not snapshot.backend.startswith("site-workspace-")
        ):
            raise ConfigurationError(
                "workspace transfer requires the same physical problem"
            )
        layout = Layout.model_validate_json(snapshot.layout_json)
        if (
            layout.width > self.backend.site.width
            or layout.height > self.backend.site.height
        ):
            raise ConfigurationError(
                "workspace transfer cannot reduce the routing grid"
            )
        mark = self.backend.mark()
        try:
            self.backend.load(replace(snapshot, backend=self.backend.name))
            checked = self.context.builder().diagnostic()
            if any(
                i.severity == "error" and i.rule != "layout.unplaced"
                for i in checked.assessment.issues
            ):
                raise FrameworkError("workspace transfer failed physical reassessment")
        except BaseException:
            self.backend.restore(mark)
            raise
        self.context.diagnostic = checked
        self.retain(checked)
