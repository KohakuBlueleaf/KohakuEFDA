"""The project's frame schema from the framework's events: a catalogue, builds, improvements, the final frame.

The studio and the viewer read frames of schema 1: the layout as JSON with its rect, the
blocks' anchors, the wires' cells, the pylons and entries, the metrics as terms. A
framework frame carries metrics and, when the sampler lets it, a layout; the observer
translates the layout it carries and fills the rest from the problem.
"""

import time
from typing import Any

from kohakuefda.model.cells import CellInstance
from kohakuefda.model.cells import Netlist as ProjectNetlist
from kohakuefda.model.dataset import Dataset
from kohakuefda.physics.fabric import area_rect, entry_rect, slots_of
from kohakuefda.physics.facts import facts
from kohakuefda.synth.layout import Translation
from kohakuefda.synth.problem import UNPOWERED_KINDS
from kohakulayout.engine.plugins import EnginePlugin
from kohakulayout.ir import Problem

FRAME_SCHEMA = 1
KINDS = {"construct": "build", "constructed": "build", "spread": "build"}


def catalogue_of(dataset: Dataset, cells: list[CellInstance]) -> list[dict]:
    """Size, kind, group, machines and local pins of every cell, for drawing frames."""
    return [
        {
            "id": cell.id,
            "kind": cell.kind,
            "constraint": cell.constraint,
            "group": cell.group,
            "env": cell.env,
            "powered": cell.kind not in UNPOWERED_KINDS
            and any(dataset.machines[m.machine_id].needs_power for m in cell.machines),
            "width": cell.width,
            "height": cell.height,
            "machines": [
                {
                    "id": m.id,
                    "machine_id": m.machine_id,
                    "x": m.x,
                    "y": m.y,
                    "rotation": m.rotation,
                    "recipe_id": m.recipe_id,
                }
                for m in cell.machines
            ],
            "pins": [
                {
                    "id": p.id,
                    "x": p.cell[0],
                    "y": p.cell[1],
                    "edge": p.edge.value,
                    "kind": p.kind,
                    "direction": p.direction,
                    "item_id": p.item_id,
                    "alternatives": [
                        {"x": a.cell[0], "y": a.cell[1], "edge": a.edge.value}
                        for a in p.alternatives
                    ],
                }
                for p in cell.pins
            ],
        }
        for cell in cells
    ]


class LayoutEveryFrame(EnginePlugin):
    """A frame with the world's layout every ``every`` charged mutations, and a layout on every frame the solver sends."""

    name = "endfield-frames"
    priority = 10

    def __init__(self, every: int = 1) -> None:
        self.every = max(1, every)
        self.charges = 0

    def on_budget(self, ctx: Any, charge: int) -> None:
        """Every ``every`` charged mutations, a frame with the layout as it stands, mid-attempt included."""
        self.charges += 1
        if self.charges % self.every == 0:
            ctx.frame(layout=True)

    def on_frame(self, ctx: Any, frame: Any) -> Any:
        if frame.layout is None:
            return frame.model_copy(update={"layout": ctx.world.freeze()})
        return None


class Cancel(EnginePlugin):
    """Raise the project's cancellation when the run manager asks for it, at the next attempt."""

    name = "endfield-cancel"
    priority = 5

    def __init__(self, cancelled: Any, error: type[Exception]) -> None:
        self.cancelled = cancelled
        self.error = error

    def pre_attempt(self, ctx: Any, attempt: Any) -> Any:
        if self.cancelled():
            raise self.error("layout cancelled")
        return None


class FrameObserver:
    """Turns framework events into the project's frames and hands them to ``observe``."""

    def __init__(
        self,
        problem: Problem,
        dataset: Dataset,
        netlist: ProjectNetlist,
        observe: Any,
        total: int,
    ) -> None:
        self.problem = problem
        self.dataset = dataset
        self.netlist = netlist
        self.observe = observe
        self.total = total
        self.started = time.monotonic()
        self.sequence = 0
        self.last = 0.0
        self.constructed = False
        self.last_layout: Any = None
        self.last_metrics: dict[str, Any] = {}

    def emit(self, event: Any) -> None:
        if event.kind != "frame" or event.payload is None:
            return
        frame = event.payload
        if frame.layout is None:
            return
        phase = frame.phase.rsplit("/", 1)[-1]
        metrics = dict(frame.metrics)
        building = (
            int(metrics.get("missing", 0)) > 0 or int(metrics.get("unrouted", 0)) > 0
        )
        kind = "build" if building else KINDS.get(phase, "improve")
        self.send(kind, frame.layout, metrics, phase)

    def send(
        self,
        kind: str,
        layout: Any,
        metrics: dict[str, Any],
        phase: str = "",
        outcome: dict[str, Any] | None = None,
        assessment: Any = None,
    ) -> dict[str, Any]:
        """One frame of the project's schema for a framework layout; returned as well as observed."""
        now = time.monotonic() - self.started
        if kind != "final":
            self.last_layout, self.last_metrics = layout, dict(metrics)
        translation = Translation(self.problem, layout, self.dataset, self.netlist)
        project = translation.project_layout()
        x0, y0, x1, y1 = area_rect(self.problem.fabric)
        cells = {(m.x, m.y) for m in project.machines} | {
            c for s in project.segments for c in s.cells
        }
        cells = {c for c in cells if x0 <= c[0] < x1 and y0 <= c[1] < y1}
        rect = (
            [
                min(x for x, _ in cells),
                min(y for _, y in cells),
                max(x for x, _ in cells) + 1,
                max(y for _, y in cells) + 1,
            ]
            if cells
            else [x0, y0, x1, y1]
        )
        terms = translation.terms(metrics)
        wires = [
            [s.id, s.kind, s.id.rsplit(".p", 1)[0], [list(c) for c in s.cells]]
            for s in project.segments
        ]
        failed = (
            [n for n in self.problem.netlist.nets if n not in layout.wires]
            if outcome is not None
            else []
        )
        complete = (
            int(metrics.get("missing", 0)) == 0 and int(metrics.get("unrouted", 0)) == 0
        )
        frame = {
            "frame_schema": FRAME_SCHEMA,
            "kind": kind,
            "phase": (
                "final"
                if kind == "final"
                else ("construction" if kind == "build" else "improvement")
            ),
            "domain": "target",
            "display": "selected" if kind == "final" else "current",
            "layout": project.model_dump(mode="json"),
            "rect": rect,
            "fixed": (
                [
                    [x, y]
                    for x, y in sorted(
                        self.problem.fabric.regions.get("bus_fixed").cells()
                    )
                ]
                if "bus_fixed" in self.problem.fabric.regions
                else []
            ),
            "slots": [[x, y, side] for x, y, side in slots_of(self.problem.fabric)],
            "state_id": layout.digest()[:16],
            "grid": [self.problem.fabric.width, self.problem.fabric.height],
            "area": [x0, y0, x1, y1],
            "target_area": list(entry_rect(self.problem.fabric)),
            "workspace_routed": False,
            "blocks": [
                [cell_id, p.x, p.y, p.rot] for cell_id, p in layout.placements.items()
            ],
            "wires": wires,
            "placed": len(layout.placements),
            "total": self.total,
            "failed": failed,
            "clean": complete,
            "pylons": [[u.x, u.y] for u in translation.pylons()],
            "entries": [[e.id, e.x, e.y, e.edge.value] for e in project.entries],
            "terms": terms,
            "cost": terms.get("area", 0.0),
            "fits": complete
            and (assessment is None or bool(getattr(assessment, "valid", False))),
            "evidence": {
                "routed": complete,
                "geometry": "pass" if complete else "fail",
                "routing": "pass" if int(metrics.get("unrouted", 1)) == 0 else "fail",
                "rates": "unknown",
            },
            "work": {"actions": self.sequence},
            "elapsed": now,
            "duration": now - self.last,
            "sequence": self.sequence,
        }
        if outcome is not None:
            frame["outcome"] = outcome
            frame["milestone"] = "final"
        elif complete and not self.constructed:
            frame["milestone"] = "constructed"
        if complete:
            self.constructed = True
        self.last = now
        self.sequence += 1
        self.observe(frame)
        return frame

    def catalogue(self, params: dict[str, Any]) -> dict[str, Any]:
        """The first frame: the grid, the area, the slots, every block's size and pins."""
        x0, y0, x1, y1 = area_rect(self.problem.fabric)
        frame = {
            "frame_schema": FRAME_SCHEMA,
            "kind": "catalogue",
            "phase": "catalogue",
            "grid": [self.problem.fabric.width, self.problem.fabric.height],
            "area": [x0, y0, x1, y1],
            "target_area": list(entry_rect(self.problem.fabric)),
            "slots": [[x, y, side] for x, y, side in slots_of(self.problem.fabric)],
            "fixed": (
                [
                    [x, y]
                    for x, y in sorted(
                        self.problem.fabric.regions.get("bus_fixed").cells()
                    )
                ]
                if "bus_fixed" in self.problem.fabric.regions
                else []
            ),
            "blocks": catalogue_of(self.dataset, self.netlist.cells),
            "settings": dict(params),
            "physics": self.problem.physics,
            "facts": facts(self.problem.fabric).get("facts", []),
            "elapsed": 0.0,
            "duration": 0.0,
            "sequence": self.sequence,
        }
        self.sequence += 1
        self.observe(frame)
        return frame


__all__ = [
    "FRAME_SCHEMA",
    "Cancel",
    "FrameObserver",
    "LayoutEveryFrame",
    "catalogue_of",
]
