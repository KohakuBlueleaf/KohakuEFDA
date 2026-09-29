"""The pipeline as four stages with checkpoints: plan, netlist, layout, verify.

Each stage reads the checkpoints before it and its parameters (``DEFAULTS``, a choice
parameter's values in ``CHOICES``) and returns the next. The netlist stage's
``transport`` picks the instances: ``legacy`` machines at nominal rates, ``rated``
exact operating points with full lanes before a partial one, ``direct`` the rated
netlist re-laned by the transport allocator. ``layout`` also takes an observer that
receives frames and a cancellation check; it states the netlist to KohakuLayout through
the synth and the Endfield pack, runs the framework solver the settings name, and
translates the layout back. Frames: one ``catalogue`` frame, ``build`` and ``improve``
frames as the solver's phases sample them, and one ``final`` frame. The verify stage's
``initial`` starts the routed evaluation from empty runs or from every net's declared
flow.
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
from kohakuefda.plan.netlist import TRANSPORT, build_netlist
from kohakuefda.plan.planner import plan as plan_scenario
from kohakuefda.plan.units import extract
from kohakuefda.synth import problem_of
from kohakuefda.synth.frames import Cancel, FrameObserver, LayoutEveryFrame
from kohakuefda.synth.layout import layout_of
from kohakuefda.synth.modules import modules_of
from kohakuefda.verify.complexity import complexity, with_units
from kohakuefda.verify.evaluate import evaluate
from kohakuefda.verify.layout import check_layout
from kohakuefda.verify.report import Report
from kohakuefda.verify.rules.rates import rate_findings
from kohakulayout.engine import CallbackSink
from kohakulayout.engine.plugins import FrameSampler, default_plugins
from kohakulayout.flow.initial import MODES
from kohakulayout.pipeline import solve

log = logging.getLogger(__name__)
STAGES = ("plan", "netlist", "layout", "verify")
CHOICES: dict[str, dict[str, tuple[str, ...]]] = {
    "netlist": {"transport": TRANSPORT},
    "verify": {"initial": MODES},
}
DEFAULTS: dict[str, dict] = {
    "plan": {},
    "netlist": {"transport": TRANSPORT[0]},
    "layout": dict(LAYOUT_DEFAULTS),
    "verify": {"initial": MODES[0]},
}


class StageError(ValueError):
    """A stage name or parameter the pipeline does not know."""


def params_of(stage: str, given: dict | None = None) -> dict:
    """The stage's defaults overridden by ``given``, each value cast to the default's type and a choice checked."""
    if stage not in DEFAULTS:
        raise StageError(f"unknown stage {stage!r}")
    try:
        out = settings_of(DEFAULTS[stage], given)
        for key, allowed in CHOICES.get(stage, {}).items():
            if out[key] not in allowed:
                raise ConfigurationError(f"{key}: {out[key]!r} is not one of {allowed}")
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


def netlist_stage(
    dataset: Dataset, scenario: Scenario, plan: Plan, params: dict | None = None
) -> Netlist:
    transport = params_of("netlist", params)["transport"]
    log.info(
        "netlist stage",
        status=plan.status,
        recipes=len(plan.recipes),
        transport=transport,
    )
    return build_netlist(dataset, scenario, plan, transport)


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
    status = "budget_exhausted" if result.context.budget.exhausted() else result.outcome
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
    params: dict | None = None,
) -> tuple[Report, Evaluation | None]:
    """Geometry rules, steady state and the rate rule over everything the run produced."""
    initial = params_of("verify", params)["initial"]
    log.info("verify stage", layout=layout is not None, initial=initial)
    scenario = netlist.scenario
    subject = f"{scenario.basement.basement_id} L{scenario.basement.level}"
    findings: list[Finding] = list(netlist.findings)
    if placement is not None:
        findings += placement.findings
    findings += extra or []
    evaluation: Evaluation | None = None
    if layout is not None:
        findings += check_layout(dataset, layout)
        evaluation = evaluate(dataset, layout, initial)
        findings += rate_findings(dataset, plan, evaluation)
    report = Report(
        subject=subject,
        dataset_version=dataset.version.id,
        findings=findings,
        complexity=(
            with_units(complexity(layout), extract(dataset, plan))
            if layout is not None
            else None
        ),
    )
    return report, evaluation
