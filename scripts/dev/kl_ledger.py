"""The KohakuLayout benchmark ledger: record what every bench printed, fail when a value moves.

    python scripts/dev/kl_ledger.py --record LEDGER      # run every bench, write the ledger
    python scripts/dev/kl_ledger.py --compare [LEDGER]   # run every bench, compare to the ledger

A bench is a script under ``tests/kohakulayout/bench/`` printing ``metric <name> <value>``
lines. Integers (counts, areas, attempts) must match exactly and fail the tier when they
move; timings are reported when they move by more than ``FLOAT_TOLERANCE`` and never fail,
because a shared machine moves them by that much between two runs. Take the ledger before
a refactor; afterwards there is nothing left to compare against.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BENCH_DIR = ROOT / "tests" / "kohakulayout" / "bench"
DEFAULT_LEDGER = BENCH_DIR / "ledger.json"
_VENV = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
PY = str(_VENV) if _VENV.exists() else sys.executable
FLOAT_TOLERANCE = 0.5


def run_benches() -> dict[str, dict[str, float | int]]:
    out: dict[str, dict[str, float | int]] = {}
    for script in sorted(BENCH_DIR.glob("bench_*.py")):
        done = subprocess.run(
            [PY, str(script)], cwd=ROOT, capture_output=True, text=True, check=False
        )
        metrics: dict[str, float | int] = {}
        for line in done.stdout.splitlines():
            parts = line.split()
            if len(parts) == 3 and parts[0] == "metric":
                value = parts[2]
                metrics[parts[1]] = (
                    int(value) if value.lstrip("-").isdigit() else float(value)
                )
        if done.returncode != 0:
            metrics["_failed"] = 1
        out[script.stem] = metrics
    return out


def compare(current: dict, ledger: dict) -> tuple[list[str], list[str]]:
    """``(failures, moved)``: an integer that changed fails; a timing outside the tolerance is only reported."""
    failures: list[str] = []
    moved: list[str] = []
    for bench, metrics in current.items():
        for name, value in metrics.items():
            was = ledger.get(bench, {}).get(name)
            if was is None:
                continue
            if isinstance(value, int) and isinstance(was, int):
                if value != was:
                    failures.append(f"{bench}.{name}: was {was}, now {value}")
            elif was and abs(value - was) / abs(was) > FLOAT_TOLERANCE:
                moved.append(f"{bench}.{name}: was {was}, now {value}")
    return failures, moved


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--record", metavar="LEDGER")
    parser.add_argument(
        "--compare", nargs="?", const=str(DEFAULT_LEDGER), metavar="LEDGER"
    )
    args = parser.parse_args(argv)
    current = run_benches()
    if not current:
        print("kl_ledger: no benches under tests/kohakulayout/bench; nothing measured")
        return 1
    for bench, metrics in current.items():
        for name, value in metrics.items():
            print(f"{bench}.{name} = {value}")
    if args.record:
        Path(args.record).write_text(
            json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"kl_ledger: recorded {args.record}")
        return 0
    if args.compare:
        ledger_path = Path(args.compare)
        if not ledger_path.exists():
            print(f"kl_ledger: no ledger at {ledger_path}; record one first")
            return 1
        failures, moved = compare(
            current, json.loads(ledger_path.read_text(encoding="utf-8"))
        )
        for line in failures:
            print("DRIFT " + line)
        for line in moved:
            print("MOVED " + line)
        print(
            f"kl_ledger: {len(failures)} changed count(s), {len(moved)} moved timing(s)"
        )
        failed = any("_failed" in m for m in current.values())
        return 1 if failures or failed else 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
