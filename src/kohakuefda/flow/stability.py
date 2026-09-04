"""Steady-state stability findings over a plan's item balances."""

import logging
from fractions import Fraction

from kohakuefda.model.dataset import Dataset
from kohakuefda.model.plan import Finding, ItemBalance, RecipeUse, TargetResult
from kohakuefda.model.scenario import Scenario

log = logging.getLogger(__name__)
AREA_WARN_FRACTION = Fraction(7, 10)


def _name(dataset: Dataset, item_id: str) -> str:
    return dataset.items[item_id].names.en


def _log_raised(findings: list[Finding]) -> None:
    for f in findings:
        log.debug("%s [%s] %s: %s", f.rule, f.severity, f.subject, f.message)


def balance_findings(dataset: Dataset, items: dict[str, ItemBalance]) -> list[Finding]:
    """Net-rate signs and sink kinds per item."""
    out: list[Finding] = []
    for balance in items.values():
        item = dataset.items[balance.item_id]
        name = item.names.en
        if balance.net > 0:
            out.append(
                Finding(
                    rule="flow.accumulates",
                    severity="error",
                    subject=balance.item_id,
                    message=f"{name} accumulates at {balance.net}/min with no sink; the lane will back up",
                )
            )
        elif balance.net < 0:
            out.append(
                Finding(
                    rule="flow.starves",
                    severity="error",
                    subject=balance.item_id,
                    message=f"{name} is short by {-balance.net}/min; consumers will starve",
                )
            )
        if balance.sunk > 0 and balance.sink_kind == "depot":
            out.append(
                Finding(
                    rule="flow.depot_sink",
                    severity="info",
                    subject=balance.item_id,
                    message=f"{balance.sunk}/min of {name} goes to the depot and will fill it over time",
                )
            )
        if balance.sunk > 0 and balance.sink_kind == "dump":
            out.append(
                Finding(
                    rule="flow.dump_sink",
                    severity="info",
                    subject=balance.item_id,
                    message=f"{balance.sunk}/min of {name} is destroyed by Water Treatment Units",
                )
            )
        if item.phase.is_fluid and balance.delivered > 0:
            out.append(
                Finding(
                    rule="flow.fluid_target",
                    severity="warning",
                    subject=balance.item_id,
                    message=f"{name} is a fluid target; it cannot be stored, something must consume it",
                )
            )
    _log_raised(out)
    return out


def target_findings(dataset: Dataset, targets: list[TargetResult]) -> list[Finding]:
    out: list[Finding] = []
    for result in targets:
        if result.achieved < result.requested:
            out.append(
                Finding(
                    rule="plan.degraded",
                    severity="warning",
                    subject=result.item_id,
                    message=(
                        f"{_name(dataset, result.item_id)}: requested {result.requested}/min, "
                        f"achievable {result.achieved}/min"
                    ),
                )
            )
    _log_raised(out)
    return out


def resource_findings(
    dataset: Dataset,
    scenario: Scenario,
    recipes: list[RecipeUse],
    power: int,
    footprint: int,
) -> list[Finding]:
    """The total power requirement, footprint against the basement square, activation."""
    out: list[Finding] = [
        Finding(
            rule="plan.power",
            severity="info",
            subject="power",
            message=f"the machines need {power} power in total",
        )
    ]
    basement = dataset.basements.get(scenario.basement.basement_id)
    square = basement.square(scenario.basement.level) if basement else None
    if square is not None:
        area = square[0] * square[1]
        if footprint > area * AREA_WARN_FRACTION:
            out.append(
                Finding(
                    rule="plan.area",
                    severity="warning",
                    subject="area",
                    message=f"machines cover {footprint} cells of a {square[0]}x{square[1]} basement; routing room is tight",
                )
            )
    for use in recipes:
        activation = dataset.activations.get(use.machine_id)
        if activation and use.machines:
            out.append(
                Finding(
                    rule="flow.activation",
                    severity="info",
                    subject=use.recipe_id,
                    message=(
                        f"{use.machines} × {dataset.machines[use.machine_id].names.en} need a continuous "
                        f"{activation.min_rate}/min of {_name(dataset, activation.item_id)} each"
                    ),
                )
            )
    _log_raised(out)
    return out
