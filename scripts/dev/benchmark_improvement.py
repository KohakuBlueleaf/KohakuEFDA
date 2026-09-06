"""Compare HC/SA compaction from identical recorded routed seeds and budgets."""

import json
import subprocess
from dataclasses import asdict
from pathlib import Path

import typer
from rich.console import Console

from kohakuefda.framework import problem_of
from kohakuefda.framework.checkpoint import SNAPSHOT, save_snapshot
from kohakuefda.framework.runtime import Runner
from kohakuefda.model.cells import Netlist
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.plan import Plan
from kohakuefda.solvers import SOLVERS
from kohakuefda.util.logging import setup

DATASET = Path("data/1.5.3@9764758-3/dataset.json")
SOURCE = Path("out/hc-sa-time-v1")
SOURCE_SOLVER = "hc"
CASES = "valley6:0,valley6:1,valley12:0,wuling6:0,wuling6:1"
OUT = Path("out/local-area-comparison")
SECONDS = 30.0
MAX_ACTIONS = 0
STEPS = 100000
BACKEND = "native"
PROFILES = "hc-control,hc,sa-control,sa"
CHECKPOINTS = (10, 30, 60, 120, 180, 300)
OLD_OPTIONS = {
    "repack_every": 0,
    "compaction_moves": False,
    "wire_tiebreak": 0.0,
    "layout_cooling_work": 100000,
    "layout_final_temperature": 0.0001,
}
CONFIGS = {
    "hc-control": ("hc", OLD_OPTIONS),
    "hc": ("hc", {}),
    "sa-control": ("sa", OLD_OPTIONS),
    "sa": ("sa", {}),
    "hc-compact": ("hc", {"repack_every": 0}),
    "sa-compact": ("sa", {"repack_every": 0}),
}
console = Console()


def save_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=1) + "\n", encoding="utf-8")


def run_profile(problem, snapshot, name, seed, settings, steps, directory):
    solver_name, options = CONFIGS[name]
    solver = SOLVERS.get(solver_name).build({"improvement_steps": steps, **options})
    world = json.loads(snapshot.payload)["settings"]
    events = []
    curve = []

    def observe(event):
        if event.kind == "transition":
            events.append({"elapsed": event.elapsed, **json.loads(event.payload_json)})
        best = runner.context.best_routed
        if best is not None and (not curve or curve[-1]["snapshot"] != best.id):
            curve.append(
                {
                    "elapsed": event.elapsed,
                    "snapshot": best.id,
                    "metrics": dict(best.assessment.metrics),
                    "work": dict(runner.context.budget.work),
                }
            )

    runner = Runner(
        problem, settings={**settings, "seed": seed}, world=world, observe=observe
    )
    result = runner.run(solver, seed=snapshot)
    best = result.best_routed
    if best is not None:
        save_snapshot(best, directory / "best.json")
    if result.current is not None:
        save_snapshot(result.current, directory / "current.json")
    save_json(directory / "transitions.json", events)
    save_json(directory / "best-curve.json", curve)
    checkpoints = []
    for checkpoint in CHECKPOINTS:
        if checkpoint > result.elapsed:
            continue
        available = [entry for entry in curve if entry["elapsed"] <= checkpoint]
        checkpoints.append(
            {"seconds": checkpoint, "best": available[-1] if available else None}
        )
    row = {
        "profile": name,
        "solver": solver_name,
        "seed": seed,
        "problem": problem.id,
        "initial_snapshot": snapshot.id,
        "status": result.status,
        "seconds": result.elapsed,
        "work": dict(result.work),
        "initial_metrics": dict(snapshot.assessment.metrics),
        "best_metrics": dict(best.assessment.metrics) if best else None,
        "assessment": asdict(best.assessment) if best else None,
        "routed": best is not None,
        "settings": json.loads(result.settings_json),
        "checkpoints": checkpoints,
    }
    save_json(directory / "result.json", row)
    return row


def main(
    source: Path = SOURCE,
    source_solver: str = SOURCE_SOLVER,
    cases: str = CASES,
    output: Path = OUT,
    seconds: float = SECONDS,
    max_actions: int = MAX_ACTIONS,
    steps: int = STEPS,
    backend: str = BACKEND,
    profiles: str = PROFILES,
    dataset_path: Path = DATASET,
) -> None:
    """Compare recorded first layouts; control profiles restore the original HC/SA moves."""
    setup("WARNING")
    names = profiles.split(",")
    if set(names) - CONFIGS.keys():
        raise typer.BadParameter("unknown comparison profile")
    if seconds < 0 or max_actions < 0 or steps < 1 or not (seconds or max_actions):
        raise typer.BadParameter(
            "require positive steps and a positive time or action ceiling"
        )
    if output.exists():
        raise typer.BadParameter("choose a fresh output directory")
    dataset = Dataset.load(dataset_path)
    inputs = []
    for entry in cases.split(","):
        name, seed_text = entry.rsplit(":", 1)
        seed = int(seed_text)
        directory = source / name
        planned = Plan.load(directory / "plan.json")
        netlist = Netlist.load(directory / "netlist.json")
        snapshot = SNAPSHOT.validate_json(
            (directory / source_solver / str(seed) / "first/snapshot.json").read_text()
        )
        if not snapshot.assessment.routed:
            raise typer.BadParameter(f"{entry} has no routed first snapshot")
        inputs.append((name, seed, problem_of(dataset, netlist, planned), snapshot))
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
            "source": str(source),
            "source_solver": source_solver,
            "profiles": names,
            "cases": cases,
            "settings": settings,
            "steps": steps,
            "phase": "improvement-only; seed reconstruction included; no rate acceptance or construction claim",
        },
    )
    rows = []
    for name, seed, problem, snapshot in inputs:
        directory = output / name / str(seed)
        directory.mkdir(parents=True)
        save_json(directory / "problem.json", asdict(problem))
        save_snapshot(snapshot, directory / "initial.json")
        for profile in names:
            target = directory / profile
            target.mkdir()
            row = run_profile(problem, snapshot, profile, seed, settings, steps, target)
            row["case"] = name
            rows.append(row)
            save_json(output / "summary.json", rows)
            area = row["best_metrics"]["area"] if row["best_metrics"] else "no result"
            console.print(
                f"{name}:{seed} {profile}: {row['initial_metrics']['area']:.0f} -> {area}, {row['seconds']:.2f}s"
            )


if __name__ == "__main__":
    typer.run(main)
