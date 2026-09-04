"""Scenario → verified layout in one call, built on the four stages."""

import logging
import time
from collections.abc import Callable

from kohakuefda.flow.evaluate import Evaluation
from kohakuefda.layout.stages import (
    layout_stage,
    netlist_stage,
    plan_stage,
    verify_stage,
)
from kohakuefda.model.cells import Netlist
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.layout import Layout
from kohakuefda.model.placement import Placement
from kohakuefda.model.plan import Plan
from kohakuefda.model.scenario import Scenario
from kohakuefda.verify.report import Report

log = logging.getLogger(__name__)
Progress = Callable[[str], None]


class LayoutResult:
    """Everything the pipeline produced; ``frames`` holds the recorded layout frames."""

    def __init__(
        self,
        plan: Plan,
        netlist: Netlist,
        placement: Placement | None,
        layout: Layout | None,
        report: Report,
        evaluation: Evaluation | None,
        frames: dict[str, list[dict]] | None = None,
    ) -> None:
        self.plan = plan
        self.netlist = netlist
        self.placement = placement
        self.layout = layout
        self.report = report
        self.evaluation = evaluation
        self.frames = frames or {}


def layout_scenario(
    dataset: Dataset,
    scenario: Scenario,
    params: dict | None = None,
    progress: Progress | None = None,
    record_frames: bool = False,
) -> LayoutResult:
    """Run every stage; an infeasible plan or a netlist with errors stops before the layout.

    ``params`` override the layout stage's defaults; ``progress`` receives a short stage name
    each time a stage starts.
    """
    report_stage = progress or (lambda stage: None)
    frames: dict[str, list[dict]] = {"layout": []}
    started = time.monotonic()
    log.info(
        "run started",
        targets=",".join(scenario.targets) or "none",
        basement=scenario.basement.basement_id,
        dataset=dataset.version.id,
    )
    report_stage("planning")
    plan = plan_stage(dataset, scenario)
    report_stage("building the netlist")
    netlist = netlist_stage(dataset, scenario, plan)
    if plan.status == "infeasible" or netlist.errors:
        report, _ = verify_stage(dataset, plan, netlist, None, None)
        log.warning(
            "run stopped before the layout",
            status=plan.status,
            errors=len(netlist.errors),
            seconds=round(time.monotonic() - started, 1),
        )
        return LayoutResult(plan, netlist, None, None, report, None)
    report_stage("laying out")
    placement, layout = layout_stage(
        dataset, netlist, params, frames["layout"].append if record_frames else None
    )
    report_stage("verifying")
    report, evaluation = verify_stage(dataset, plan, netlist, placement, layout)
    errors = [f for f in report.findings if f.severity == "error"]
    log.info(
        "run finished" if not errors else "run finished with errors",
        seconds=round(time.monotonic() - started, 1),
        errors=len(errors),
        findings=len(report.findings),
        converged=evaluation.converged if evaluation else None,
    )
    return LayoutResult(plan, netlist, placement, layout, report, evaluation, frames)
