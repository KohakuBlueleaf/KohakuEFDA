"""Equal-budget dense battery runs through the layout stage, with post-search rate evidence.

Construction/search uses the same seconds and action ceilings for every solver.
Rate evaluation runs afterwards on the first observed and best routed layouts;
it never turns a partial diagnostic into a success or hides material findings.
"""

import json
import platform
import subprocess
import time
from pathlib import Path

import typer
from rich.console import Console

from kohakuefda.layout.board import board_of
from kohakuefda.layout.settings import LayoutError, framework_id, solver_of
from kohakuefda.layout.stages import StageError, layout_stage
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.layout import Layout
from kohakuefda.model.scenario import Scenario
from kohakuefda.plan.netlist import build_netlist
from kohakuefda.plan.planner import plan
from kohakuefda.synth import problem_of
from kohakuefda.util.logging import setup
from kohakuefda.verify.evaluate import evaluate
from kohakuefda.verify.rules.rates import rate_findings

DATASET = Path("data/1.5.3@9764758-3/dataset.json")
FIXTURES = Path("tests/fixtures")
CASES = "valley6,valley12,valley18,wuling6,wuling12"
SCENARIOS = {case: f"scenario_dense_{case}.toml" for case in CASES.split(",")}
SCENARIOS["wuling50"] = "scenario_wuling_battery50.toml"
SOLVER_NAMES = "baseline"
SEEDS = "0,1,2"
SECONDS = 60.0
MAX_ACTIONS = 0
BACKEND = "auto"
OUT = Path("out/dense-benchmarks")
VERIFY_RATES = True
SOLVER_OPTIONS = "{}"
FRAME_EVERY = 100_000
FRAME_KEYS = ("kind", "phase", "elapsed", "sequence", "milestone", "outcome")

console = Console()


def save_json(path: Path, value) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def rate_evidence(dataset, result, layout: Layout, directory: Path) -> dict:
    """Evaluate one routed layout after search and retain every rate finding."""
    started = time.monotonic()
    evaluated = evaluate(dataset, layout)
    findings = rate_findings(dataset, result, evaluated)
    save_json(directory / "evaluation.json", evaluated.model_dump(mode="json"))
    save_json(directory / "rate-findings.json", [f.model_dump() for f in findings])
    return {
        "status": "fail" if any(f.severity == "error" for f in findings) else "pass",
        "seconds": time.monotonic() - started,
        "findings": [f.model_dump() for f in findings],
    }


def save_snapshot(directory: Path, layout: Layout, terms: dict, placement=None) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "layout.json").write_text(
        layout.model_dump_json(indent=1), encoding="utf-8"
    )
    save_json(directory / "terms.json", terms)
    if placement is not None:
        (directory / "placement.json").write_text(
            placement.model_dump_json(indent=1), encoding="utf-8"
        )


def run_case(
    dataset,
    netlist,
    result,
    problem_id,
    name,
    seed,
    settings,
    directory,
    verify_rates,
    solver_options=None,
):
    """Run one solver through the layout stage; save first-observed, best and diagnostic evidence."""
    frames: list[dict] = []
    first: dict | None = None
    final: dict | None = None

    def observe(frame: dict) -> None:
        nonlocal first, final
        frames.append({k: frame[k] for k in FRAME_KEYS if k in frame})
        if frame["kind"] == "final":
            final = frame
        elif first is None and frame.get("evidence", {}).get("routed"):
            first = frame

    params = {
        **settings,
        "solver": name,
        "seed": seed,
        "frame_every": FRAME_EVERY,
        "solver_options": json.dumps((solver_options or {}).get(name, {})),
    }
    started = time.monotonic()
    error = None
    placement = layout = None
    try:
        placement, layout = layout_stage(dataset, netlist, params, observe=observe)
    except (LayoutError, StageError) as failure:
        error = str(failure)
    elapsed = time.monotonic() - started
    outcome = (final or {}).get("outcome", {})
    routed = bool(outcome.get("routed")) and layout is not None
    if routed and first is None:
        first = final
    row = {
        "solver": name,
        "seed": seed,
        "problem_id": problem_id,
        "status": outcome.get("status", "error" if error else "unknown"),
        "error": error,
        "search_seconds": elapsed,
        "work": dict(outcome.get("work", {})),
        "settings": dict(outcome.get("settings", {})),
        "routed": routed,
        "first_observed_routed_seconds": first["elapsed"] if first else None,
        "first_verified_during_search_seconds": None,
        "verification_phase": "post-search",
        "rates": "not_checked",
        "verified": False,
        "metrics": dict(final["terms"]) if routed and final else None,
    }
    snapshots: dict[str, Layout | None] = {
        "first": Layout.model_validate(first["layout"]) if first else None,
        "best": layout if routed else None,
        "diagnostic": (
            Layout.model_validate(final["layout"]) if final and not routed else None
        ),
    }
    if first is not None:
        save_snapshot(directory / "first", snapshots["first"], first["terms"])
    if routed:
        save_snapshot(directory / "best", layout, final["terms"], placement)
    if snapshots["diagnostic"] is not None:
        save_snapshot(directory / "diagnostic", snapshots["diagnostic"], final["terms"])
    save_json(directory / "events.json", frames)
    save_json(directory / "result.json", row)
    if verify_rates:
        checked: dict[str, dict] = {}
        for label in ("first", "best"):
            snapshot = snapshots[label]
            if snapshot is None:
                continue
            key = snapshot.model_dump_json()
            if key not in checked:
                checked[key] = rate_evidence(
                    dataset, result, snapshot, directory / label
                )
            row[f"{label}_rate_check"] = checked[key]
        if routed:
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
    solver_options: str = SOLVER_OPTIONS,
) -> None:
    """Benchmark selected comma-separated cases, layout-stage solvers and integer seeds."""
    setup("WARNING")
    selected = cases.split(",")
    names = solvers.split(",")
    seed_values = [int(seed) for seed in seeds.split(",")]
    if set(selected) - SCENARIOS.keys():
        raise typer.BadParameter("unknown dense battery case")
    try:
        options = json.loads(solver_options)
    except ValueError as error:
        raise typer.BadParameter("solver-options must be a JSON object") from error
    if not isinstance(options, dict) or any(
        not isinstance(value, dict) for value in options.values()
    ):
        raise typer.BadParameter("solver-options maps solver names to settings objects")
    if set(options) - set(names):
        raise typer.BadParameter("solver-options includes an unselected solver")
    try:
        for name in names:
            framework_id(name)
            solver_of(
                {"solver": name, "solver_options": json.dumps(options.get(name, {}))}
            )
    except LayoutError as error:
        raise typer.BadParameter(str(error)) from error
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
            "settings": {**settings, "check_rates": False},
            "solver_options": options,
            "timing": "Serial search; first routed timestamp is the first routed frame. Rate checks are post-search, not time-to-first-verified search results.",
        },
    )
    rows = []
    for case in selected:
        directory = output / case
        directory.mkdir()
        scenario = Scenario.from_toml(FIXTURES / SCENARIOS[case])
        result = plan(dataset, scenario)
        netlist = build_netlist(dataset, scenario, result)
        problem_id = problem_of(dataset, netlist, board_of(dataset, scenario)).digest()
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
                    netlist,
                    result,
                    problem_id,
                    name,
                    seed,
                    settings,
                    run_dir,
                    verify_rates,
                    options,
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
