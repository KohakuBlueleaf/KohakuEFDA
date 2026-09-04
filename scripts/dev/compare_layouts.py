"""Every scenario laid out by both paths, with everything each run knows written to disk."""

import json
import logging
import sys
import time
from pathlib import Path

from kohakuefda.layout.pipeline import layout_scenario
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.scenario import Scenario
from kohakuefda.util.logging import setup

log = logging.getLogger(__name__)
DATASET = Path("data/1.5.3@9764758-3/dataset.json")
FIXTURES = Path("tests/fixtures")
SCENARIOS = (
    "scenario_gas_xiranite",
    "scenario_valley_battery",
    "scenario_wuling_hetonite",
    "scenario_basic",
)
PATHS = {"baseline": {"heuristic": "off"}, "heuristic": {"heuristic": "anneal"}}
OUT = Path(".internal/plans/progress/compare.json")


def main() -> int:
    setup("WARNING")
    dataset = Dataset.load(DATASET)
    rows = []
    for name in SCENARIOS:
        scenario = Scenario.from_toml(FIXTURES / f"{name}.toml")
        for path, params in PATHS.items():
            clock = time.monotonic()
            result = layout_scenario(dataset, scenario, params)
            terms = result.placement.terms
            errors = [
                f.rule
                for f in result.report.findings
                if f.severity == "error" and not f.rule.startswith("flow.")
            ]
            row = {
                "scenario": name,
                "path": path,
                "seconds": round(time.monotonic() - clock, 1),
                "area": int(terms["area"]),
                "wires": int(terms["length"]),
                "machines": len(result.layout.machines),
                "errors": errors,
            }
            rows.append(row)
            print(json.dumps(row), flush=True)
            OUT.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
