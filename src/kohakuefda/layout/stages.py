"""The pipeline as four stages with checkpoints: plan, netlist, layout, verify.

Each stage reads the checkpoints before it and returns the next. ``layout`` takes a parameter
dict (defaults in ``DEFAULTS``), an observer that receives frames, and a cancellation check;
it states the netlist to KohakuLayout through the synth and the Endfield pack, runs the
framework solver the settings name, and translates the layout back. Frames: one
``catalogue`` frame (grid, area, slots, block sizes and pins), ``build`` and ``improve``
frames as the solver's phases sample them, and one ``final`` frame.
"""

import logging

from kohakuefda.flow.evaluate import Evaluation
from kohakuefda.layout.board import board_of
from kohakuefda.layout.settings import (
    LAYOUT_DEFAULTS,
    ConfigurationError,
    LayoutError,
    budget_of,
    router_of,
    settings_of,
    solver_of,
)
from kohakuefda.model.cells import Netlist
from kohakuefda.model.control import Cancelled, CancelledError, Observe
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.layout import Layout
from kohakuefda.model.placement import Placement
from kohakuefda.model.plan import Finding, Plan
from kohakuefda.model.scenario import Scenario
from kohakuefda.plan.netlist import build_netlist
from kohakuefda.plan.planner import plan as plan_scenario
from kohakuefda.synth import problem_of
from kohakuefda.synth.frames import Cancel, FrameObserver, LayoutEveryFrame
from kohakuefda.synth.layout import layout_of
from kohakuefda.synth.modules import modules_of
from kohakuefda.verify.evaluate import evaluate
from kohakuefda.verify.layout import check_layout
from kohakuefda.verify.report import Report
from kohakuefda.verify.rules.rates import rate_findings
from kohakulayout.engine import CallbackSink
from kohakulayout.engine.plugins import FrameSampler, default_plugins
from kohakulayout.pipeline import solve

log = logging.getLogger(__name__)
STAGES = ("plan", "netlist", "layout", "verify")
DEFAULTS: dict[str, dict] = {
    "plan": {},
    "netlist": {},
    "layout": dict(LAYOUT_DEFAULTS),
    "verify": {},
}


class StageError(ValueError):
    """A stage name or parameter the pipeline does not know."""


def params_of(stage: str, given: dict | None = None) -> dict:
    """The stage's defaults overridden by ``given``, each value cast to the default's type."""
    if stage not in DEFAULTS:
        raise StageError(f"unknown stage {stage!r}")
    try:
        out = settings_of(DEFAULTS[stage], given)
        if stage == "layout":
            solver_of(out)
        return out
    except ConfigurationError as error:
        raise StageError(f"{stage} parameters: {error}") from error


def plan_stage(dataset: Dataset, scenario: Scenario) -> Plan:
    log.info(
        "plan stage",
        targets=len(scenario.targets),
        supply=len(scenario.supply),
        mode=scenario.mode,
        basement=scenario.basement.basement_id,
        dataset=dataset.version.id,
    )
    return plan_scenario(dataset, scenario)


def netlist_stage(dataset: Dataset, scenario: Scenario, plan: Plan) -> Netlist:
    log.info("netlist stage", status=plan.status, recipes=len(plan.recipes))
    return build_netlist(dataset, scenario, plan)


def outcome_of(
    status: str,
    metrics: dict,
    settings: dict,
    options: dict,
    total: int,
    routed: bool = False,
    actions: int = 0,
    attempts: int = 0,
    refusals: int = 0,
) -> dict:
    """What the run manager records about a layout run: how it ended, what stood, what it cost."""
    placed = int(metrics.get("placed", 0))
    return {
        "status": status,
        "routed": bool(routed),
        "placed": placed,
        "total": total,
        "work": {
            "actions": int(actions),
            "attempts": int(attempts),
            "refusals": int(refusals),
        },
        "settings": {"runtime": dict(settings), "solver_settings": dict(options)},
    }


def layout_stage(
    dataset: Dataset,
    netlist: Netlist,
    params: dict | None = None,
    observe: Observe | None = None,
    cancelled: Cancelled | None = None,
) -> tuple[Placement, Layout]:
    """Run the framework on the synth's problem; returns the placement checkpoint and the routed layout."""
    settings = params_of("layout", params)
    scenario = netlist.scenario
    board = board_of(dataset, scenario)
    log.info(
        "layout stage",
        cells=len(netlist.cells),
        nets=len(netlist.nets),
        square=f"{board.square[0]}x{board.square[1]}",
        slots=len(board.slots),
    )
    problem = problem_of(dataset, netlist, board)
    solver_id, options = solver_of(settings)
    observer = FrameObserver(
        problem, dataset, netlist, observe or (lambda frame: None), len(netlist.cells)
    )
    if observe is not None:
        observer.catalogue(settings)
    plugins = [*default_plugins()]
    if observe is not None:
        plugins = [
            FrameSampler(layout_every=1) if p.name == "sampler" else p for p in plugins
        ]
        plugins.append(LayoutEveryFrame(int(settings["frame_every"])))
    if cancelled is not None:
        plugins.append(Cancel(cancelled, CancelledError))
    budget = budget_of(settings)
    try:
        result = solve(
            problem,
            solver=solver_id,
            seed=int(settings["seed"]),
            budget=budget,
            params=options,
            plugins=plugins,
            progress=CallbackSink(observer.emit) if observe is not None else None,
            kernel=str(settings["backend"]),
            workers=max(1, int(settings["workers"])),
            router=router_of(),
        )
    except CancelledError:
        if observe is not None and observer.last_layout is not None:
            outcome = outcome_of(
                "cancelled",
                observer.last_metrics,
                settings,
                options,
                len(netlist.cells),
            )
            observer.send(
                "final", observer.last_layout, observer.last_metrics, "final", outcome
            )
        raise
    if result.layout is None:
        raise LayoutError(f"no layout produced: {result.outcome}")
    metrics = dict(result.assessment.metrics)
    status = "budget_exhausted" if result.context.budget.exhausted else result.outcome
    outcome = outcome_of(
        status,
        metrics,
        settings,
        options,
        len(netlist.cells),
        routed=result.assessment.valid,
        actions=result.context.budget.used,
        attempts=result.attempts,
        refusals=result.refusals,
    )
    if observe is not None:
        observer.send(
            "final", result.layout, metrics, "final", outcome, result.assessment
        )
    placement, layout = layout_of(
        problem, result.layout, dataset, netlist, result.assessment
    )
    layout.modules = modules_of(dataset, layout)
    layout.notes = (
        f"{scenario.basement.basement_id} level {scenario.basement.level}, "
        f"solver {settings['solver']}, seed {settings['seed']}, "
        f"time budget {settings['seconds']}s, action budget {settings['max_actions']}"
    )
    return placement, layout


def verify_stage(
    dataset: Dataset,
    plan: Plan,
    netlist: Netlist,
    placement: Placement | None,
    layout: Layout | None,
    extra: list[Finding] | None = None,
) -> tuple[Report, Evaluation | None]:
    """Geometry rules, steady state and the rate rule over everything the run produced."""
    log.info("verify stage", layout=layout is not None, rates=layout is not None)
    scenario = netlist.scenario
    subject = f"{scenario.basement.basement_id} L{scenario.basement.level}"
    findings: list[Finding] = list(netlist.findings)
    if placement is not None:
        findings += placement.findings
    findings += extra or []
    evaluation: Evaluation | None = None
    if layout is not None:
        findings += check_layout(dataset, layout)
        evaluation = evaluate(dataset, layout)
        findings += rate_findings(dataset, plan, evaluation)
    report = Report(
        subject=subject, dataset_version=dataset.version.id, findings=findings
    )
    return report, evaluation
