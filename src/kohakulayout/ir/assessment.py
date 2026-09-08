"""L1: what a layout is worth and what it violates."""

from typing import ClassVar, Literal

from kohakulayout.ir.base import Attrs, Level, Model, Rate, check_attrs

Severity = Literal["error", "warning", "info"]
SEVERITIES: tuple[str, ...] = ("error", "warning", "info")

FRAMEWORK_METRICS: tuple[str, ...] = (
    "placed",
    "missing",
    "routed",
    "unrouted",
    "extent_w",
    "extent_h",
    "area",
    "wire_cells",
    "units",
    "overflow",
)


class Finding(Model):
    rule: str
    severity: Severity
    subject: str
    message: str
    attrs: Attrs = {}


class Assessment(Level):
    level: ClassVar[str] = "assessment"
    layout: str = ""
    metrics: dict[str, int | Rate] = {}
    findings: tuple[Finding, ...] = ()
    complete: bool = False
    valid: bool = False

    def check(self) -> list[str]:
        problems: list[str] = []
        for name in FRAMEWORK_METRICS:
            if name not in self.metrics:
                problems.append(f"assessment: framework metric {name!r} is missing")
        for finding in self.findings:
            if not finding.rule:
                problems.append("assessment: a finding has no rule id")
            problems += check_attrs(finding.attrs, f"finding {finding.rule}")
        errors = any(f.severity == "error" for f in self.findings)
        if self.valid and (not self.complete or errors):
            problems.append("assessment: valid requires complete and no error finding")
        return problems

    def errors(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.severity == "error")
