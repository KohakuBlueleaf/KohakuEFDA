"""Rate rules over an evaluated layout: every recipe runs at the plan's machine-equivalents,
sources run, and the steady state converges."""

import logging
from fractions import Fraction

from kohakuefda.flow.evaluate import EPSILON, Evaluation
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.plan import Finding, Plan

log = logging.getLogger(__name__)
RATE_TOLERANCE = EPSILON


def rate_findings(
    dataset: Dataset, plan: Plan, evaluation: Evaluation
) -> list[Finding]:
    """Findings over an evaluation; a shortfall within ``RATE_TOLERANCE`` machine-equivalents
    is the relaxation's stopping tolerance, not starvation."""
    out: list[Finding] = []
    if not evaluation.converged:
        out.append(
            Finding(
                rule="flow.unconverged",
                severity="error",
                subject="layout",
                message=f"steady state not reached in {evaluation.iterations} iterations",
            )
        )
    running: dict[str, Fraction] = {}
    stalled: dict[str, list[str]] = {}
    for state in evaluation.machines.values():
        if state.recipe_id is None:
            if state.utilisation == 0 and state.stalled_by:
                out.append(
                    Finding(
                        rule="flow.idle",
                        severity="warning",
                        subject=state.placed_id,
                        message=f"{state.placed_id} ({dataset.machines[state.machine_id].names.en}): {state.stalled_by}",
                    )
                )
            continue
        running[state.recipe_id] = (
            running.get(state.recipe_id, Fraction(0)) + state.utilisation
        )
        if state.stalled_by:
            stalled.setdefault(state.recipe_id, []).append(
                f"{state.placed_id}: {state.stalled_by}"
            )
    for use in plan.recipes:
        if use.recipe_id.startswith("dump:"):
            continue
        achieved = running.get(use.recipe_id, Fraction(0))
        if achieved + RATE_TOLERANCE < use.machines_exact:
            detail = "; ".join(stalled.get(use.recipe_id, [])[:3])
            out.append(
                Finding(
                    rule="flow.starved",
                    severity="error",
                    subject=use.recipe_id,
                    message=(
                        f"{use.recipe_id} runs {achieved} machine-equivalents, the plan needs {use.machines_exact}"
                        + (f" ({detail})" if detail else "")
                    ),
                )
            )
    for f in out:
        log.debug("%s [%s] %s: %s", f.rule, f.severity, f.subject, f.message)
    log.info(
        "rate check: %d finding(s) over %d machine(s)",
        len(out),
        len(evaluation.machines),
    )
    return out
