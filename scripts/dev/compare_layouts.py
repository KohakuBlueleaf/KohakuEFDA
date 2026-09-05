"""Benchmark baseline settings on the bundled scenarios, preserving all verification findings."""

import json
import sys
import time
from pathlib import Path

from kohakuefda.layout.pipeline import layout_scenario
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.scenario import Scenario
from kohakuefda.util.logging import setup

DATASET = Path("data/1.5.3@9764758-3/dataset.json")
FIXTURES = Path("tests/fixtures")
SCENARIOS = (
    "scenario_gas_xiranite",
    "scenario_valley_battery",
    "scenario_wuling_hetonite",
    "scenario_basic",
    "scenario_hub_battery",
)
PATHS = {"baseline": {"workers": 1}}
OUT = Path("out/baseline-benchmarks")


def main() -> int:
    setup("WARNING")
    dataset = Dataset.load(DATASET)
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for name in SCENARIOS:
        scenario = Scenario.from_toml(FIXTURES / f"{name}.toml")
        for path, params in PATHS.items():
            clock = time.monotonic()
            result = layout_scenario(dataset, scenario, params)
            terms = result.placement.terms if result.placement else {}
            errors = [f for f in result.report.findings if f.severity == "error"]
            row = {
                "scenario": name,
                "path": path,
                "seconds": round(time.monotonic() - clock, 2),
                "terms": terms,
                "geometry_errors": [
                    f.rule for f in errors if not f.rule.startswith("flow.")
                ],
                "flow_errors": [f.rule for f in errors if f.rule.startswith("flow.")],
            }
            directory = OUT / name / path
            directory.mkdir(parents=True, exist_ok=True)
            for artifact in (
                "plan",
                "netlist",
                "placement",
                "layout",
                "report",
                "evaluation",
            ):
                value = getattr(result, artifact)
                if value is not None:
                    (directory / f"{artifact}.json").write_text(
                        value.model_dump_json(indent=1), encoding="utf-8"
                    )
            rows.append(row)
            print(json.dumps(row), flush=True)
            (OUT / "summary.json").write_text(
                json.dumps(rows, indent=2), encoding="utf-8"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
