"""Write ``tests/fixtures/endfield_basic.kl``: the basic scenario as the synth states it to KohakuLayout.

    python scripts/dev/endfield_fixture.py

Run it again whenever the synth or the pack changes what the problem holds; the test
``test_the_fixture_is_the_synth_output`` compares digests.
"""

import sys
from pathlib import Path

from kohakuefda.layout.stages import netlist_stage, plan_stage
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.scenario import Scenario
from kohakuefda.synth import problem_of

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "data" / "1.5.3@9764758-3" / "dataset.json"
SCENARIO = ROOT / "tests" / "fixtures" / "scenario_basic.toml"
FIXTURE = ROOT / "tests" / "fixtures" / "endfield_basic.kl"


def main() -> int:
    dataset = Dataset.load(DATASET)
    scenario = Scenario.from_toml(SCENARIO)
    netlist = netlist_stage(dataset, scenario, plan_stage(dataset, scenario))
    problem = problem_of(dataset, netlist)
    FIXTURE.write_text(problem.text(), encoding="utf-8")
    print(
        f"wrote {FIXTURE} ({len(problem.netlist.cells)} cells, {len(problem.netlist.nets)} nets)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
