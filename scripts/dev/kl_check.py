"""Run one tier of the KohakuLayout checks, bounded, and report a hang as a hang.

    python scripts/dev/kl_check.py [fast|unit|journey|bench|full] [-j N]

    fast      black, ruff, the comment budget, kl_deps, the isolation test, the unit tests
    unit      fast plus the integration tests
    journey   unit plus the service journeys
    bench     the native module present, the parity suite, the ledger against its baseline
    full      all of the above

Every check is bounded: one that produces no result inside its budget is killed and
reported as STALLED, a different event from a FAIL. A tier that is empty fails. Exits
non-zero when any check failed or stalled.
"""

import argparse
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_VENV = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
PY = str(_VENV) if _VENV.exists() else sys.executable
DEFAULT_TIMEOUT = 600
TIMEOUTS: dict[str, int] = {"bench": 1800}

FRAMEWORK_PATHS = ["src/kohakulayout", "tests/kohakulayout"]
DEV_SCRIPTS = sorted(
    str(p.relative_to(ROOT)) for p in (ROOT / "scripts" / "dev").glob("kl_*.py")
)
HOOKS = sorted(
    str(p.relative_to(ROOT)) for p in (ROOT / ".claude" / "hooks").glob("*.py")
)


def py(label: str, *args: str) -> dict:
    return {"label": label, "argv": [PY, *args]}


def cmd(label: str, *argv: str) -> dict:
    return {"label": label, "argv": list(argv)}


FAST = [
    py("black", "-m", "black", "--check", "-q", *FRAMEWORK_PATHS, *DEV_SCRIPTS, *HOOKS),
    py("ruff", "-m", "ruff", "check", *FRAMEWORK_PATHS, *DEV_SCRIPTS, *HOOKS),
    py(
        "comment budget",
        "scripts/dev/comment_budget.py",
        *FRAMEWORK_PATHS,
        "scripts/dev",
    ),
    py("kl_deps", "scripts/dev/kl_deps.py"),
    py("isolation", "-m", "pytest", "tests/kohakulayout/test_isolation.py", "-q"),
    py("unit", "-m", "pytest", "tests/kohakulayout/unit", "-q"),
]
UNIT = FAST + [
    py("integration", "-m", "pytest", "tests/kohakulayout/integration", "-q")
]
JOURNEY = UNIT + [
    py("journey", "-m", "pytest", "tests/kohakulayout/journey", "-q", "-m", "journey")
]
BENCH = [
    py("native", "-c", "import kohakulayout_rs"),
    cmd(
        "cargo fmt",
        "cargo",
        "fmt",
        "--check",
        "--manifest-path",
        "src/kohakulayout-rs/Cargo.toml",
    ),
    cmd(
        "cargo clippy",
        "cargo",
        "clippy",
        "--release",
        "--manifest-path",
        "src/kohakulayout-rs/Cargo.toml",
        "--",
        "-D",
        "warnings",
    ),
    py("parity", "-m", "pytest", "tests/kohakulayout/parity", "-q"),
    py("bench", "scripts/dev/kl_ledger.py", "--compare"),
]
TIERS = {
    "fast": FAST,
    "unit": UNIT,
    "journey": JOURNEY,
    "bench": BENCH,
    "full": JOURNEY + BENCH,
}


def run(check: dict) -> tuple[str, str, float, str]:
    label = check["label"]
    budget = TIMEOUTS.get(label, DEFAULT_TIMEOUT)
    started = time.perf_counter()
    try:
        done = subprocess.run(
            check["argv"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=budget,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return (
            label,
            "STALLED",
            time.perf_counter() - started,
            f"no result inside {budget}s",
        )
    status = "PASS" if done.returncode == 0 else "FAIL"
    tail = (done.stdout + done.stderr).strip().splitlines()[-25:]
    return label, status, time.perf_counter() - started, "\n".join(tail)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tier", nargs="?", default="fast", choices=sorted(TIERS))
    parser.add_argument("-j", type=int, default=4)
    args = parser.parse_args(argv)
    checks = TIERS[args.tier]
    if not checks:
        print(f"tier {args.tier!r} is empty, which is a failure, not a pass")
        return 1
    with ThreadPoolExecutor(max_workers=args.j) as pool:
        results = list(pool.map(run, checks))
    bad = 0
    for label, status, seconds, tail in results:
        print(f"{status:8} {seconds:7.1f}s  {label}")
        if status != "PASS":
            bad += 1
            print("\n".join("    " + line for line in tail.splitlines()))
    print(f"kl_check {args.tier}: {len(results) - bad}/{len(results)} passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
