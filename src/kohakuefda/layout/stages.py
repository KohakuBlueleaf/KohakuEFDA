"""The pipeline as four stages with checkpoints: plan, netlist, layout, verify.

Each stage reads the checkpoints before it and returns the next. ``layout`` takes a parameter
dict (defaults in ``DEFAULTS``), an observer that receives frames, and a cancellation check.
Frames: one ``catalogue`` frame (grid, area, slots, block sizes and pins), a ``build`` frame per
machine placed and wired, an ``improve`` frame whenever a move betters the layout, and one
``final`` frame.
"""

import logging

from kohakuefda.flow.evaluate import Evaluation, evaluate
from kohakuefda.layout.board import Board, board_of
from kohakuefda.layout.engine import LAYOUT_DEFAULTS, Engine
from kohakuefda.layout.place import Block, placement_of
from kohakuefda.model.cells import Netlist
from kohakuefda.model.control import Cancelled, Observe
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.layout import Layout
from kohakuefda.model.placement import Placement
from kohakuefda.model.plan import Finding, Plan
from kohakuefda.model.scenario import Scenario
from kohakuefda.plan.netlist import build_netlist
from kohakuefda.plan.planner import plan as plan_scenario
from kohakuefda.verify.report import Report
from kohakuefda.verify.rules.geometry import check_layout
from kohakuefda.verify.rules.rates import rate_findings

log = logging.getLogger(__name__)
STAGES = ("plan", "netlist", "layout", "verify")
DEFAULTS: dict[str, dict] = {
    "plan": {},
    "netlist": {},
    "layout": dict(LAYOUT_DEFAULTS),
    "verify": {},
}
__all__ = ["Board", "blocks_of", "board_of"]


class StageError(ValueError):
    """A stage name or parameter the pipeline does not know."""


def params_of(stage: str, given: dict | None = None) -> dict:
    """The stage's defaults overridden by ``given``, each value cast to the default's type."""
    if stage not in DEFAULTS:
        raise StageError(f"unknown stage {stage!r}")
    defaults = DEFAULTS[stage]
    out = dict(defaults)
    for key, value in (given or {}).items():
        if key not in defaults:
            raise StageError(f"unknown {stage} parameter {key!r}")
        try:
            out[key] = type(defaults[key])(value)
        except (TypeError, ValueError) as error:
            raise StageError(f"{stage} parameter {key!r}: {error}") from error
    return out


def blocks_of(dataset: Dataset, netlist: Netlist) -> list[Block]:
    return [Block.of_cell(c, dataset) for c in netlist.cells]


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


def layout_stage(
    dataset: Dataset,
    netlist: Netlist,
    params: dict | None = None,
    observe: Observe | None = None,
    cancelled: Cancelled | None = None,
) -> tuple[Placement, Layout]:
    """Run the engine; returns the placement checkpoint and the routed layout."""
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
    engine = Engine(dataset, netlist, board, settings)
    result = engine.run(observe, cancelled)
    layout = result.layout
    layout.notes = (
        f"{scenario.basement.basement_id} level {scenario.basement.level}, "
        f"seed {settings['seed']}, {settings['spread_attempts']} attempts"
    )
    placement = placement_of(
        result.blocks,
        result.pylons,
        result.entries,
        dataset.version.id,
        board.square,
        (layout.width, layout.height),
        layout.area_rect,
        0,
        result.cost,
        result.terms,
        result.findings,
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
