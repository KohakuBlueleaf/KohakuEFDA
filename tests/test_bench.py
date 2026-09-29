"""The bench keeps failed trials, refuses to overwrite evidence and bounds its workers."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "dev" / "bench" / "run.py"


def bench(*args: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "run", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def test_an_exhausted_trial_is_kept_without_a_verified_winner(tmp_path) -> None:
    output = tmp_path / "bench"
    args = (
        "--cases",
        "dense_valley6",
        "--transports",
        "direct",
        "--solvers",
        "guided",
        "--seeds",
        "0",
        "--seconds",
        "0.02",
        "--actions",
        "1",
        "--workers",
        "1",
        "--backend",
        "python",
        "--output",
        str(output),
    )
    result = bench(*args)
    assert result.returncode == 0, result.stdout + result.stderr

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["workers"] == 1 and manifest["actions"] == 1
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    (row,) = summary["runs"]
    assert not row["verified"] and "best" not in row
    assert summary["winners"] == {}
    assert summary["reliability"][0]["trials"] == 1
    assert (output / "dense_valley6" / "direct" / "netlist.json").exists()
    assert (output / "report.html").exists()

    before = (output / "summary.json").read_bytes()
    assert bench(*args, timeout=30).returncode != 0
    assert (output / "summary.json").read_bytes() == before


def test_the_worker_cap_is_checked_before_any_output(tmp_path) -> None:
    output = tmp_path / "unsafe"
    result = bench("--workers", "999", "--output", str(output), timeout=30)
    assert result.returncode != 0
    assert not output.exists()
