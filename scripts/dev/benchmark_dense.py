"""Equal-budget dense battery runs with separate post-search production evidence.

Construction/search uses the same seconds and action ceilings for every solver.
Rate evaluation runs afterwards on the first observed and best routed artifacts;
it never turns a partial diagnostic into a success or hides material findings.
"""

import json
import platform
import subprocess
import time
from dataclasses import asdict
from pathlib import Path

import typer
from rich.console import Console

from kohakuefda.flow.evaluate import evaluate
from kohakuefda.framework import problem_of
from kohakuefda.framework.runtime import Runner
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.layout import Layout
from kohakuefda.model.scenario import Scenario
from kohakuefda.plan.netlist import build_netlist
from kohakuefda.plan.planner import plan
from kohakuefda.solvers import SOLVERS
from kohakuefda.util.logging import setup
from kohakuefda.verify.rules.rates import rate_findings

DATASET = Path("data/1.5.3@9764758-3/dataset.json")
FIXTURES = Path("tests/fixtures")
CASES = "valley6,valley12,valley18,wuling6,wuling12"
SOLVER_NAMES = "baseline"
SEEDS = "0,1,2"
SECONDS = 60.0
MAX_ACTIONS = 0
BACKEND = "native"
OUT = Path("out/dense-benchmarks")
VERIFY_RATES = True
SOLVER_SETTINGS = {}
WORLD = {"frame_every": 100000}
console = Console()


def save_json(path: Path, value) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def rate_evidence(dataset, result, snapshot, directory: Path) -> dict:
    """Evaluate one routed artifact after search and retain every rate finding."""
    started = time.monotonic()
    layout = Layout.model_validate_json(snapshot.layout_json)
    evaluated = evaluate(dataset, layout)
    findings = rate_findings(dataset, result, evaluated)
    save_json(directory / "evaluation.json", evaluated.model_dump(mode="json"))
    save_json(directory / "rate-findings.json", [f.model_dump() for f in findings])
    return {
        "status": "fail" if any(f.severity == "error" for f in findings) else "pass",
        "seconds": time.monotonic() - started,
        "findings": [f.model_dump() for f in findings],
    }


def run_case(dataset, problem, result, name, seed, settings, directory, verify_rates):
    """Run a catalog solver and save first-observed, best and diagnostic evidence."""
    first = None
    first_elapsed = None
    events = []

    def observe(event):
        nonlocal first, first_elapsed
        events.append({"kind": event.kind, "elapsed": event.elapsed})
        if first is None and runner.context.best_routed is not None:
            first = runner.context.best_routed
            first_elapsed = event.elapsed

    solver = SOLVERS.get(name).build(SOLVER_SETTINGS.get(name))
    runner = Runner(
        problem, settings={**settings, "seed": seed}, world=WORLD, observe=observe
    )
    solved = runner.run(solver, strict=False)
    if first is None and solved.best_routed is not None:
        first, first_elapsed = solved.best_routed, solved.elapsed
    row = {
        "solver": name,
        "seed": seed,
        "problem_id": problem.id,
        "status": solved.status,
        "error": solved.error,
        "search_seconds": solved.elapsed,
        "work": dict(solved.work),
        "settings": json.loads(solved.settings_json),
        "routed": solved.best_routed is not None,
        "first_observed_routed_seconds": first_elapsed,
        "first_verified_during_search_seconds": None,
        "verification_phase": "post-search",
        "rates": "not_checked",
        "verified": False,
        "metrics": (
            dict(solved.best_routed.assessment.metrics) if solved.best_routed else None
        ),
    }
    snapshots = {
        "first": first,
        "best": solved.best_routed,
        "diagnostic": solved.current,
    }
    for label, snapshot in snapshots.items():
        if snapshot is None:
            continue
        target = directory / label
        target.mkdir(parents=True, exist_ok=True)
        save_json(target / "snapshot.json", asdict(snapshot))
        (target / "layout.json").write_text(snapshot.layout_json, encoding="utf-8")
        (target / "placement.json").write_text(
            snapshot.placement_json, encoding="utf-8"
        )
        save_json(target / "assessment.json", asdict(snapshot.assessment))
    save_json(directory / "events.json", events)
    save_json(directory / "result.json", row)
    checked = {}
    if verify_rates:
        for label in ("first", "best"):
            snapshot = snapshots[label]
            if snapshot is None:
                continue
            if snapshot.id not in checked:
                checked[snapshot.id] = rate_evidence(
                    dataset, result, snapshot, directory / label
                )
            evidence = checked[snapshot.id]
            row[f"{label}_rate_check"] = evidence
        if solved.best_routed:
            row["rates"] = row["best_rate_check"]["status"]
            row["verified"] = row["rates"] == "pass"
    save_json(directory / "result.json", row)
    return row


def reliability(rows: list[dict]) -> list[dict]:
    """Counts and denominator for each scenario/solver pair, including failed runs."""
    keys = sorted({(row["case"], row["solver"]) for row in rows})
    return [
        {
            "case": case,
            "solver": solver,
            "runs": len(group),
            "routed": sum(row["routed"] for row in group),
            "verified": sum(row["verified"] for row in group),
        }
        for case, solver in keys
        if (
            group := [
                row for row in rows if (row["case"], row["solver"]) == (case, solver)
            ]
        )
    ]


def main(
    cases: str = CASES,
    solvers: str = SOLVER_NAMES,
    seeds: str = SEEDS,
    seconds: float = SECONDS,
    max_actions: int = MAX_ACTIONS,
    backend: str = BACKEND,
    output: Path = OUT,
    dataset_path: Path = DATASET,
    verify_rates: bool = VERIFY_RATES,
) -> None:
    """Benchmark selected comma-separated cases, catalog solvers and integer seeds."""
    setup("WARNING")
    selected = cases.split(",")
    names = solvers.split(",")
    seed_values = [int(seed) for seed in seeds.split(",")]
    if set(selected) - set(CASES.split(",")):
        raise typer.BadParameter("unknown dense battery case")
    for name in names:
        SOLVERS.get(name)
    if seconds < 0 or max_actions < 0 or not (seconds or max_actions):
        raise typer.BadParameter("set a positive seconds or action ceiling")
    if output.exists():
        raise typer.BadParameter("output exists; choose a fresh evidence directory")
    dataset = Dataset.load(dataset_path)
    output.mkdir(parents=True)
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--porcelain"], capture_output=True, text=True, check=True
    ).stdout
    settings = {
        "seconds": seconds,
        "max_actions": max_actions,
        "backend": backend,
        "workers": 1,
        "check_rates": False,
    }
    save_json(
        output / "manifest.json",
        {
            "revision": revision,
            "working_tree": dirty,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "dataset_version": dataset.version.id,
            "cases": selected,
            "solvers": names,
            "seeds": seed_values,
            "settings": settings,
            "timing": "Serial search; first routed timestamp is first observer notification. Rate checks are post-search, not time-to-first-verified search results.",
        },
    )
    rows = []
    for case in selected:
        directory = output / case
        directory.mkdir()
        scenario = Scenario.from_toml(FIXTURES / f"scenario_dense_{case}.toml")
        result = plan(dataset, scenario)
        netlist = build_netlist(dataset, scenario, result)
        problem = problem_of(dataset, netlist, result)
        (directory / "scenario.toml").write_text(scenario.to_toml(), encoding="utf-8")
        result.save(directory / "plan.json")
        (directory / "netlist.json").write_text(
            netlist.model_dump_json(indent=1), encoding="utf-8"
        )
        for seed in seed_values:
            for name in names:
                run_dir = directory / name / str(seed)
                run_dir.mkdir(parents=True)
                row = run_case(
                    dataset,
                    problem,
                    result,
                    name,
                    seed,
                    settings,
                    run_dir,
                    verify_rates,
                )
                row["case"] = case
                row["cells"] = len(netlist.cells)
                rows.append(row)
                save_json(
                    output / "summary.json",
                    {"runs": rows, "reliability": reliability(rows)},
                )
                console.print(
                    f"{case} {name} seed={seed}: {row['status']}, routed={row['routed']}, rates={row['rates']}, {row['search_seconds']:.2f}s"
                )


if __name__ == "__main__":
    typer.run(main)
