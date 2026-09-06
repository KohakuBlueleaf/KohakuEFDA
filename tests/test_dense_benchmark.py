"""The benchmark preserves failed trials and refuses evidence-directory reuse."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "dev" / "benchmark_dense.py"


def test_dense_benchmark_records_exhaustion_without_claiming_a_solution(tmp_path):
    output = tmp_path / "evidence"
    command = [
        sys.executable,
        str(SCRIPT),
        "--cases",
        "valley12",
        "--seeds",
        "0,1",
        "--seconds",
        "0",
        "--max-actions",
        "1",
        "--backend",
        "python",
        "--output",
        str(output),
    ]
    completed = subprocess.run(
        command, cwd=ROOT, capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0, completed.stderr
    summary = json.loads((output / "summary.json").read_text())
    rows = summary["runs"]
    assert len(rows) == 2
    assert {row["seed"] for row in rows} == {0, 1}
    assert len({row["problem_id"] for row in rows}) == 1
    for row in rows:
        assert row["status"] == "budget_exhausted"
        assert not row["routed"]
        assert not row["verified"]
        assert row["rates"] == "not_checked"
        assert row["first_observed_routed_seconds"] is None
        assert row["first_verified_during_search_seconds"] is None
        assert row["metrics"] is None
        assert row["work"]["actions"] == 1
    assert summary["reliability"] == [
        {
            "case": "valley12",
            "solver": "baseline",
            "runs": 2,
            "routed": 0,
            "verified": 0,
        }
    ]
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["settings"]["workers"] == 1
    assert manifest["settings"]["max_actions"] == 1
    assert not manifest["settings"]["check_rates"]
    assert (output / "valley12" / "plan.json").exists()
    assert (output / "valley12" / "netlist.json").exists()
    before = (output / "summary.json").read_bytes()
    repeated = subprocess.run(
        command, cwd=ROOT, capture_output=True, text=True, check=False
    )
    assert repeated.returncode != 0
    assert (output / "summary.json").read_bytes() == before


def test_local_benchmark_options_and_interrupted_lineage_are_saved(tmp_path):
    output = tmp_path / "local"
    options = {"hc": {"construction_steps": 2}, "sa": {"construction_steps": 2}}
    command = [
        sys.executable,
        str(SCRIPT),
        "--cases",
        "valley6",
        "--seeds",
        "0",
        "--solvers",
        "hc,sa",
        "--seconds",
        "0",
        "--max-actions",
        "1",
        "--backend",
        "python",
        "--solver-options",
        json.dumps(options),
        "--output",
        str(output),
    ]
    result = subprocess.run(
        command, cwd=ROOT, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["solver_options"] == options
    for name in ("hc", "sa"):
        events = json.loads((output / "valley6" / name / "0/events.json").read_text())
        transitions = [
            event["payload"] for event in events if event["kind"] == "transition"
        ]
        assert transitions and transitions[-1]["outcome"] == "interrupted"
        assert transitions[-1]["parent"] == transitions[-1]["next_parent"]
        assert not transitions[-1]["accepted"]
