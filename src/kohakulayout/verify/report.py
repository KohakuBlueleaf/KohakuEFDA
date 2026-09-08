"""A plain-text report of an assessment: verdict, metrics, findings."""

from kohakulayout.ir import Assessment
from kohakulayout.ir.base import rate_text


def report(assessment: Assessment) -> str:
    verdict = (
        "valid"
        if assessment.valid
        else ("complete" if assessment.complete else "incomplete")
    )
    lines = [f"assessment {assessment.layout[:12]}: {verdict}"]
    for name, value in sorted(assessment.metrics.items()):
        text = value if isinstance(value, int) else rate_text(value)
        lines.append(f"  {name} = {text}")
    for finding in assessment.findings:
        lines.append(
            f"  {finding.severity} {finding.rule} {finding.subject}: {finding.message}"
        )
    return "\n".join(lines)


__all__ = ["report"]
