"""The verification report: findings over a layout or plan."""

import json
import logging
from pathlib import Path

from kohakuefda.model.base import EfdaModel
from kohakuefda.model.plan import Finding

log = logging.getLogger(__name__)


class Report(EfdaModel):
    """Findings with a verdict; ``ok`` means no error-severity finding."""

    schema_version: int = 1
    subject: str
    dataset_version: str
    findings: list[Finding] = []

    @property
    def ok(self) -> bool:
        return not any(f.severity == "error" for f in self.findings)

    def count(self, severity: str) -> int:
        return sum(1 for f in self.findings if f.severity == severity)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=1) + "\n", encoding="utf-8")
        log.info(
            "report %s: %d error(s), %d warning(s), %d info -> %s",
            self.subject,
            self.count("error"),
            self.count("warning"),
            self.count("info"),
            path,
        )

    @classmethod
    def load(cls, path: Path) -> "Report":
        report = cls.model_validate(json.loads(path.read_text(encoding="utf-8")))
        log.debug("loaded report %s from %s", report.subject, path)
        return report
