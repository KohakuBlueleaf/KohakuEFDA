"""Compatibility adapter from the layout stage to the solver framework."""

import json

from kohakuefda.framework.config import RUNTIME_DEFAULTS, WORLD_DEFAULTS, settings_of
from kohakuefda.framework.control import ConfigurationError
from kohakuefda.framework.problem import problem_of
from kohakuefda.framework.runtime import Runner
from kohakuefda.layout.board import Board
from kohakuefda.model.cells import Netlist
from kohakuefda.model.control import CancelledError
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.layout import Layout
from kohakuefda.model.placement import Placement
from kohakuefda.model.plan import Finding
from kohakuefda.solvers import SOLVERS
from kohakuefda.solvers.baseline import DEFAULTS

LAYOUT_DEFAULTS = {
    **WORLD_DEFAULTS,
    **DEFAULTS,
    **{k: v for k, v in RUNTIME_DEFAULTS.items() if k != "check_rates"},
    "solver": "baseline",
    "solver_options": "{}",
}
LayoutError = ConfigurationError


class EngineResult:
    """Legacy stage output backed by a framework snapshot and assessment."""

    def __init__(self, runner: Runner, snapshot) -> None:
        self.layout = Layout.model_validate_json(snapshot.layout_json)
        self.placement = Placement.model_validate_json(snapshot.placement_json)
        self.blocks = list(runner.backend.site.blocks.values())
        self.wires = runner.backend.site.wires
        self.pylons = self.placement.pylons
        self.entries = self.layout.entries
        self.terms = dict(snapshot.assessment.metrics)
        self.cost = self.terms["area"]
        self.findings = [
            Finding(
                rule=i.rule, severity=i.severity, subject=i.subject, message=i.message
            )
            for i in snapshot.assessment.issues
        ]
        self.fits = snapshot.assessment.geometry == "pass"


class Engine:
    """Stage composition root; concrete strategy comes from the solver catalog."""

    def __init__(
        self, dataset: Dataset, netlist: Netlist, board: Board, params: dict
    ) -> None:
        self.params = settings_of(LAYOUT_DEFAULTS, params)
        self.problem = problem_of(dataset, netlist)
        self.board = board
        entry = SOLVERS.get(self.params["solver"])
        options = json.loads(self.params["solver_options"])
        if not isinstance(options, dict):
            raise ConfigurationError("solver_options must be a JSON object")
        self.solver = entry.build(
            {
                **{k: self.params[k] for k in entry.defaults if k in self.params},
                **options,
            }
        )
        self.runner = None
        self.site = None
        self.spread = None

    def _runner(self, observe=None, cancelled=None) -> Runner:
        def watch(event):
            payload = json.loads(event.payload_json)
            if payload.get("kind") in ("catalogue", "build", "improve", "selected"):
                payload.update(
                    elapsed=event.elapsed,
                    duration=event.duration,
                    sequence=event.sequence,
                )
                if payload["kind"] == "selected":
                    payload["kind"] = "final"
                observe(payload)

        return Runner(
            self.problem,
            settings={
                **{k: self.params[k] for k in RUNTIME_DEFAULTS if k in self.params},
                "check_rates": False,
            },
            world={k: self.params[k] for k in WORLD_DEFAULTS},
            observe=watch if observe else None,
            cancelled=cancelled,
        )

    def run(self, observe=None, cancelled=None) -> EngineResult:
        self.runner = self._runner(observe, cancelled)
        result = self.runner.run(self.solver)
        self.site = self.runner.backend.site
        self.spread = getattr(self.solver, "spread", None)
        if result.status == "cancelled":
            raise CancelledError("layout cancelled")
        snapshot = result.best_routed or result.current
        if snapshot is None:
            raise LayoutError(f"no layout produced: {result.status}")
        selected = EngineResult(self.runner, snapshot)
        frame = self.runner.backend.snapshot_frame(snapshot, "selected")
        frame["status"] = result.status
        self.runner.context.emit("selected", frame)
        return selected

    def kinds(self, *constraints):
        return [b for b in self.site.blocks.values() if b.constraint in constraints]

    def measure(self, site):
        snapshot = self.runner.backend.capture()
        metrics = dict(snapshot.assessment.metrics)
        return (
            len(site.unplaced()),
            len(site.unrouted()),
            metrics["area"],
            metrics["wire_path_cells"],
        )
