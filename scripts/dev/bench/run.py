"""Layout portfolios: cases × transports × solvers × seeds, each trial in its own process,
every trial's layouts, findings and flow checks on disk, a ledger and a report."""

import hashlib
import html
import json
import math
import os
import platform
import subprocess
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import typer

from kohakuefda.layout.settings import solver_of
from kohakuefda.layout.stages import CHOICES, layout_stage, netlist_stage
from kohakuefda.model.cells import Netlist
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.layout import Layout
from kohakuefda.model.plan import Plan
from kohakuefda.model.scenario import Scenario
from kohakuefda.plan.planner import plan
from kohakuefda.plan.units import extract
from kohakuefda.render.grid_text import render_text
from kohakuefda.util.logging import setup
from kohakuefda.verify.complexity import complexity, with_units
from kohakuefda.verify.evaluate import evaluate
from kohakuefda.verify.layout import check_layout
from kohakuefda.verify.rules.rates import rate_findings
from kohakulayout._rust import HAS_RUST

ROOT = Path(__file__).resolve().parents[3]
DATASET = ROOT / "data" / "1.5.3@9764758-3" / "dataset.json"
FIXTURES = ROOT / "tests" / "fixtures"
OUTPUT = ROOT / "out" / "bench"
CASES = "dense_valley6,dense_wuling6"
TRANSPORTS = "direct"
SOLVERS = "guided"
SEEDS = "0,1,2"
SECONDS = 60.0
ACTIONS = 60000
BACKEND = "auto"
WORKERS = 4
MAX_WORKERS = 8
TIMEOUT_SLACK = 60.0
FRAME_EVERY = 100_000
FRAME_KEYS = ("kind", "phase", "elapsed", "sequence", "milestone", "outcome")
LOG_LEVEL = "WARNING"
app = typer.Typer(add_completion=False)


def save(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, default=str, indent=1), encoding="utf-8")


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def source_digest() -> str:
    """The hash of every Python source file under ``src``."""
    digest = hashlib.sha256()
    for path in sorted((ROOT / "src").rglob("*.py")):
        if "__pycache__" not in path.parts:
            digest.update(path.relative_to(ROOT).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def prepare(dataset: Dataset, case: str, transport: str, directory: Path) -> None:
    """The case's scenario, plan and netlist under ``transport``, saved once for every trial."""
    fixture = FIXTURES / f"scenario_{case}.toml"
    if not fixture.exists():
        raise typer.BadParameter(f"no fixture {fixture.name}")

    directory.mkdir(parents=True)
    scenario = Scenario.from_toml(fixture)
    planned = plan(dataset, scenario)
    (directory / "scenario.toml").write_text(scenario.to_toml(), encoding="utf-8")
    planned.save(directory / "plan.json")
    if planned.status == "infeasible":
        raise typer.BadParameter(f"{case}: the plan is infeasible")
    netlist = netlist_stage(dataset, scenario, planned, {"transport": transport})
    netlist.save(directory / "netlist.json")


def flow_checks(
    dataset: Dataset, planned: Plan, layout: Layout, directory: Path
) -> dict:
    """The routed evaluation from each initial state, its convergence and rate errors."""
    out = {}
    for initial in CHOICES["verify"]["initial"]:
        evaluated = evaluate(dataset, layout, initial)
        findings = [f.model_dump() for f in rate_findings(dataset, planned, evaluated)]
        (directory / f"evaluation-{initial}.json").write_text(
            evaluated.model_dump_json(indent=1), encoding="utf-8"
        )
        save(directory / f"rates-{initial}.json", findings)
        out[initial] = {
            "converged": evaluated.converged,
            "errors": sum(f["severity"] == "error" for f in findings),
        }
    return out


def snapshot(
    dataset: Dataset, planned: Plan, layout: Layout, terms: dict, directory: Path
) -> dict:
    """One layout with its terms, geometry findings, complexity and flow checks."""
    directory.mkdir(parents=True, exist_ok=True)
    layout.save(directory / "layout.json")
    geometry = [f.model_dump() for f in check_layout(dataset, layout)]
    save(directory / "terms.json", terms)
    save(directory / "geometry.json", geometry)
    measured = with_units(complexity(layout), extract(dataset, planned))
    save(directory / "complexity.json", measured.model_dump(mode="json"))
    return {
        "terms": terms,
        "geometry_errors": sum(f["severity"] == "error" for f in geometry),
        "flow": flow_checks(dataset, planned, layout, directory),
    }


@app.command()
def worker(spec: Path) -> None:
    """Run one trial from its saved specification."""
    setup(LOG_LEVEL)
    trial = load(spec)
    directory = spec.parent
    inputs = Path(trial["inputs"])
    row: dict[str, Any] = {**trial, "verified": False, "error": None}
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

    started = time.monotonic()
    try:
        dataset = Dataset.load(DATASET)
        netlist = Netlist.load(inputs / "netlist.json")
        planned = Plan.load(inputs / "plan.json")
        params = {
            "solver": trial["solver"],
            "seed": trial["seed"],
            "seconds": trial["seconds"],
            "max_actions": trial["actions"],
            "backend": trial["backend"],
            "workers": 1,
            "frame_every": FRAME_EVERY,
            "solver_options": json.dumps(trial["options"]),
        }
        _, layout = layout_stage(dataset, netlist, params, observe=observe)
        row["seconds_used"] = time.monotonic() - started

        outcome = (final or {}).get("outcome", {})
        row["outcome"] = outcome
        routed = bool(outcome.get("routed"))
        if first is not None:
            row["first"] = snapshot(
                dataset,
                planned,
                Layout.model_validate(first["layout"]),
                first["terms"],
                directory / "first",
            )
            row["first"]["elapsed"] = first["elapsed"]
        label = "best" if routed else "diagnostic"
        row[label] = snapshot(
            dataset, planned, layout, (final or {}).get("terms", {}), directory / label
        )
        best = row.get("best")
        row["verified"] = bool(
            best
            and outcome.get("placed") == len(netlist.cells)
            and not best["geometry_errors"]
            and best["flow"]["declared"]["converged"]
            and not best["flow"]["declared"]["errors"]
        )
    except Exception as error:  # noqa: BLE001
        row["error"] = f"{type(error).__name__}: {error}"
        row["seconds_used"] = time.monotonic() - started
        (directory / "traceback.txt").write_text(
            traceback.format_exc(), encoding="utf-8"
        )

    save(directory / "events.json", frames)
    save(directory / "result.json", row)
    typer.echo(line_of(row))
    if row["error"]:
        raise typer.Exit(1)


def launch(spec: Path, seconds: float) -> dict:
    """One worker process under a hard wall-time ceiling, its output kept."""
    environment = {
        **os.environ,
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "PYTHONUTF8": "1",
        "PYTHONHASHSEED": "0",
    }
    try:
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "worker", str(spec)],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=seconds + TIMEOUT_SLACK,
            check=False,
        )
        (spec.parent / "worker.log").write_text(
            result.stdout + result.stderr, encoding="utf-8"
        )
        path = spec.parent / "result.json"
        if path.exists():
            return load(path)
        error = f"worker exited {result.returncode} without a result"
    except subprocess.TimeoutExpired:
        error = "worker passed the hard wall-time ceiling"

    row = {**load(spec), "verified": False, "error": error}
    save(spec.parent / "result.json", row)
    return row


def area_of(row: dict) -> int | None:
    return (row.get("best") or {}).get("terms", {}).get("area")


def rate_errors(row: dict, initial: str) -> int | None:
    return (row.get("best") or {}).get("flow", {}).get(initial, {}).get("errors")


LEDGER = (
    ("case", lambda r: r["case"]),
    ("transport", lambda r: r["transport"]),
    ("solver", lambda r: r["solver"]),
    ("seed", lambda r: r["seed"]),
    ("placed", lambda r: r.get("outcome", {}).get("placed")),
    ("routed", lambda r: bool(r.get("best"))),
    ("area", area_of),
    ("geometry errors", lambda r: (r.get("best") or {}).get("geometry_errors")),
    ("rate errors, empty", lambda r: rate_errors(r, "empty")),
    ("rate errors, declared", lambda r: rate_errors(r, "declared")),
    ("verified", lambda r: r.get("verified")),
    ("seconds", lambda r: round(r.get("seconds_used", 0), 1)),
    ("error", lambda r: r.get("error") or ""),
)


def line_of(row: dict) -> str:
    return (
        f"{row['case']} / {row['transport']} / {row['solver']} / {row['seed']}: "
        f"verified={row.get('verified')} area={area_of(row)} error={row.get('error')}"
    )


def winners(rows: list[dict]) -> dict[str, dict]:
    """Per case and transport the verified trial of least area, then wire, then bridges."""
    out: dict[str, dict] = {}
    for row in rows:
        if not row.get("verified"):
            continue
        key = f"{row['case']}/{row['transport']}"
        terms = row["best"]["terms"]
        rank = (terms["area"], terms.get("length", 0), terms.get("bridges", 0))
        if key not in out or rank < out[key]["rank"]:
            out[key] = {"rank": rank, **{k: row[k] for k in ("solver", "seed")}}
    return out


def reliability(rows: list[dict]) -> list[dict]:
    """Trials, routed and verified per case, transport and solver, failures counted."""
    groups: dict[tuple, list[dict]] = {}
    for row in rows:
        groups.setdefault((row["case"], row["transport"], row["solver"]), []).append(
            row
        )
    return [
        {
            "case": case,
            "transport": transport,
            "solver": solver,
            "trials": len(group),
            "routed": sum(bool(r.get("best")) for r in group),
            "verified": sum(bool(r.get("verified")) for r in group),
        }
        for (case, transport, solver), group in sorted(groups.items())
    ]


@app.command()
def report(output: Path = OUTPUT) -> None:
    """The ledger and every winner's text map as ``report.html`` in ``output``."""
    rows = load(output / "summary.json")["runs"]
    dataset = Dataset.load(DATASET)
    ordered = sorted(
        rows, key=lambda r: (r["case"], r["transport"], r["solver"], r["seed"])
    )
    cells = "".join(
        "<tr>"
        + "".join(f"<td>{html.escape(str(value(row)))}</td>" for _, value in LEDGER)
        + "</tr>"
        for row in ordered
    )
    maps = ""
    for key, win in winners(rows).items():
        case, transport = key.split("/")
        path = output / case / transport / win["solver"] / str(win["seed"]) / "best"
        text = render_text(dataset, Layout.load(path / "layout.json"))
        maps += (
            f"<h2>{html.escape(key)}: {win['solver']} seed {win['seed']}, "
            f"area {win['rank'][0]}</h2><pre>{html.escape(text)}</pre>"
        )
    page = (
        "<!doctype html><meta charset='utf-8'><title>Bench report</title>"
        "<style>body{font:14px system-ui;margin:24px}td,th{padding:2px 8px;"
        "border-bottom:1px solid #ccc}pre{font:10px/1 monospace}</style>"
        f"<h1>{html.escape(output.name)}</h1><table><tr>"
        + "".join(f"<th>{name}</th>" for name, _ in LEDGER)
        + f"</tr>{cells}</table>{maps}"
    )
    (output / "report.html").write_text(page, encoding="utf-8")
    typer.echo(f"Report: {output / 'report.html'}")


@app.command()
def run(
    cases: str = CASES,
    transports: str = TRANSPORTS,
    solvers: str = SOLVERS,
    seeds: str = SEEDS,
    seconds: float = SECONDS,
    actions: int = ACTIONS,
    workers: int = WORKERS,
    backend: str = BACKEND,
    output: Path = OUTPUT,
    options: str = "{}",
) -> None:
    """Every trial of the grid with matched inputs; the output directory must be new."""
    setup(LOG_LEVEL)
    if not 1 <= workers <= MAX_WORKERS:
        raise typer.BadParameter(f"workers must be between 1 and {MAX_WORKERS}")
    if not math.isfinite(seconds) or seconds <= 0 or actions <= 0:
        raise typer.BadParameter("seconds and actions must both be positive")
    if output.exists():
        raise typer.BadParameter("output exists; choose a new directory")

    selected = [int(seed) for seed in seeds.split(",")]
    policies = transports.split(",")
    names = solvers.split(",")
    settings = json.loads(options)
    if len(selected) != len(set(selected)):
        raise typer.BadParameter("seeds must be distinct")
    if set(policies) - set(CHOICES["netlist"]["transport"]):
        raise typer.BadParameter(f"transports: {CHOICES['netlist']['transport']}")
    if not isinstance(settings, dict) or any(
        not isinstance(v, dict) for v in settings.values()
    ):
        raise typer.BadParameter("options map solver names to option objects")
    for name in names:
        solver_of(
            {"solver": name, "solver_options": json.dumps(settings.get(name, {}))}
        )

    output.mkdir(parents=True)
    dataset = Dataset.load(DATASET)
    save(
        output / "manifest.json",
        {
            "revision": git("rev-parse", "HEAD"),
            "working_tree": git("status", "--porcelain"),
            "source_sha256": source_digest(),
            "python": sys.executable,
            "platform": platform.platform(),
            "dataset": dataset.version.id,
            "native_available": HAS_RUST,
            "cases": cases,
            "transports": transports,
            "solvers": solvers,
            "seeds": selected,
            "seconds": seconds,
            "actions": actions,
            "workers": workers,
            "backend": backend,
            "options": settings,
            "worker_hash_seed": 0,
            "numeric_thread_limit": 1,
        },
    )

    specs = []
    for case in cases.split(","):
        for transport in policies:
            inputs = output / case / transport
            prepare(dataset, case, transport, inputs)
            for name in names:
                for seed in selected:
                    directory = inputs / name / str(seed)
                    directory.mkdir(parents=True)
                    spec = directory / "trial.json"
                    save(
                        spec,
                        {
                            "case": case,
                            "transport": transport,
                            "solver": name,
                            "seed": seed,
                            "inputs": str(inputs),
                            "seconds": seconds,
                            "actions": actions,
                            "backend": backend,
                            "options": settings.get(name, {}),
                        },
                    )
                    specs.append(spec)

    rows = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending = [pool.submit(launch, spec, seconds) for spec in specs]
        for future in as_completed(pending):
            rows.append(future.result())
            save(
                output / "summary.json",
                {
                    "runs": rows,
                    "reliability": reliability(rows),
                    "winners": winners(rows),
                },
            )
            typer.echo(line_of(rows[-1]))
    report(output)


if __name__ == "__main__":
    app()
