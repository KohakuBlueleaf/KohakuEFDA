"""``kohakuefda layout``, ``kohakuefda check`` and ``kohakuefda render``."""

import json
import logging
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from kohakuefda.cli.data import DEFAULT_ROOT, load_dataset
from kohakuefda.data.importers.industrial_planner import import_industrial_planner
from kohakuefda.flow.evaluate import Evaluation, evaluate
from kohakuefda.layout.engine import LAYOUT_DEFAULTS
from kohakuefda.layout.pipeline import layout_scenario
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.layout import Layout
from kohakuefda.model.plan import Finding
from kohakuefda.model.scenario import Scenario
from kohakuefda.render.grid_text import render_text
from kohakuefda.render.png import render_png
from kohakuefda.render.tables import findings_table
from kohakuefda.verify.report import Report
from kohakuefda.verify.rules.geometry import check_layout

log = logging.getLogger(__name__)
console = Console()


def load_layout(dataset: Dataset, path: Path) -> Layout:
    """Our layout JSON, or an IndustrialPlanner blueprint when it carries ``schemaVersion``."""
    text = path.read_text(encoding="utf-8")
    if '"schemaVersion"' in text and '"entities"' in text:
        return import_industrial_planner(dataset, path)
    return Layout.load(path)


def _print_findings(findings: list[Finding], title: str) -> None:
    errors = sum(1 for f in findings if f.severity == "error")
    warnings = sum(1 for f in findings if f.severity == "warning")
    infos = sum(1 for f in findings if f.severity == "info")
    log.info("%s: %d error(s), %d warning(s), %d info", title, errors, warnings, infos)
    console.print(
        findings_table(findings, f"{title}: {errors} errors, {warnings} warnings")
    )


def _print_rates(result: Evaluation) -> None:
    rates = Table(
        title=f"machine utilisation (converged={result.converged}, {result.iterations} iterations)"
    )
    for col in ("placed", "machine", "recipe", "utilisation", "stalled by"):
        rates.add_column(col)
    for state in result.machines.values():
        rates.add_row(
            state.placed_id,
            state.machine_id,
            state.recipe_id or "",
            str(state.utilisation),
            state.stalled_by,
        )
    console.print(rates)


def check_cmd(
    layout_file: Path = typer.Argument(
        ..., help="layout.json or an IndustrialPlanner blueprint"
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Write report.json here."
    ),
    evaluate_rates: bool = typer.Option(
        True, "--rates/--no-rates", help="Also evaluate flows."
    ),
    version: str = typer.Option("", "--version", "-v"),
    root: Path = typer.Option(DEFAULT_ROOT, "--root"),
) -> None:
    """Verify a layout against the geometry rules and report steady-state rates."""
    dataset = load_dataset(root, version)
    layout = load_layout(dataset, layout_file)
    findings = check_layout(dataset, layout)
    log.info("check %s: %d findings", layout_file, len(findings))
    report = Report(
        subject=str(layout_file), dataset_version=dataset.version.id, findings=findings
    )
    _print_findings(findings, layout_file.name)
    if evaluate_rates:
        _print_rates(evaluate(dataset, layout))
    if output is not None:
        report.save(output)
        log.info("wrote %s", output)
    if not report.ok:
        raise typer.Exit(code=1)


def render_cmd(
    layout_file: Path = typer.Argument(
        ..., help="layout.json or an IndustrialPlanner blueprint"
    ),
    png: Path | None = typer.Option(
        None, "--png", help="Write a PNG here (needs matplotlib)."
    ),
    version: str = typer.Option("", "--version", "-v"),
    root: Path = typer.Option(DEFAULT_ROOT, "--root"),
) -> None:
    """Print the layout as a text grid, optionally also as PNG."""
    dataset = load_dataset(root, version)
    layout = load_layout(dataset, layout_file)
    console.print(render_text(dataset, layout), highlight=False)
    if png is not None:
        path = render_png(dataset, layout, png)
        log.info("wrote %s", path)
        console.print(f"[green]wrote[/] {path}")


def layout_cmd(
    scenario_file: Path = typer.Argument(..., help="scenario.toml"),
    output: Path = typer.Option(
        Path("out"),
        "--output",
        "-o",
        help="Directory for plan, netlist, layout and report.",
    ),
    seed: int = typer.Option(0, "--seed", help="Search seed."),
    solver: str = typer.Option("baseline", "--solver", help="Registered solver name."),
    solver_options: str = typer.Option(
        "{}", "--solver-options", help="Solver settings as a JSON object."
    ),
    backend: str = typer.Option(
        "auto", "--backend", help="Grid backend: auto, python, native."
    ),
    seconds: float = typer.Option(
        0.0, "--seconds", help="Cooperative time budget; 0 is unlimited."
    ),
    max_actions: int = typer.Option(
        0, "--max-actions", help="Action budget; 0 is unlimited."
    ),
    attempts: int = typer.Option(
        int(LAYOUT_DEFAULTS["spread_attempts"]),
        "--attempts",
        help="Maximum spread attempts; stop at the first fully placed and routed result.",
    ),
    workers: int = typer.Option(
        int(LAYOUT_DEFAULTS["workers"]),
        "--workers",
        "-j",
        help="Searches to run at once, each from its own seed; 0 asks the machine.",
    ),
    png: bool = typer.Option(
        False, "--png", help="Also write layout.png (needs matplotlib)."
    ),
    frames: bool = typer.Option(
        False, "--frames", help="Also write frames/layout.json."
    ),
    version: str = typer.Option("", "--version", "-v"),
    root: Path = typer.Option(DEFAULT_ROOT, "--root"),
) -> None:
    """Plan, lay out and verify a scenario; write the artifacts and print the checks."""
    dataset = load_dataset(root, version)
    scenario = Scenario.from_toml(scenario_file)
    params: dict = {
        "seed": seed,
        "solver": solver,
        "solver_options": solver_options,
        "backend": backend,
        "seconds": seconds,
        "max_actions": max_actions,
        "spread_attempts": attempts,
        "workers": workers,
    }
    log.info(
        "laying out a scenario",
        scenario=str(scenario_file),
        seed=seed,
        attempts=attempts,
        workers=workers or "auto",
        dataset=dataset.version.id,
    )
    started = time.monotonic()
    result = layout_scenario(dataset, scenario, params, record_frames=frames)
    log.info("layout pipeline finished in %.1fs", time.monotonic() - started)
    output.mkdir(parents=True, exist_ok=True)
    result.plan.save(output / "plan.json")
    result.netlist.save(output / "netlist.json")
    result.report.save(output / "report.json")
    if result.placement is not None:
        result.placement.save(output / "placement.json")
    if frames:
        for stage, recorded in result.frames.items():
            path = output / "frames" / f"{stage}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(recorded), encoding="utf-8")
    if result.evaluation is not None:
        (output / "evaluation.json").write_text(
            result.evaluation.model_dump_json(indent=1) + "\n", encoding="utf-8"
        )
    if result.layout is not None:
        result.layout.save(output / "layout.json")
        console.print(render_text(dataset, result.layout), highlight=False)
        modules = Table(title=f"modules: {len(result.layout.modules)}")
        for col in ("module", "origin", "size", "entities"):
            modules.add_column(col)
        for module in result.layout.modules:
            modules.add_row(
                module.id,
                f"({module.x}, {module.y})",
                f"{module.width}×{module.height}",
                str(len(module.entities)),
            )
        console.print(modules)
        if png:
            console.print(
                f"[green]wrote[/] {render_png(dataset, result.layout, output / 'layout.png')}"
            )
    if result.evaluation is not None:
        _print_rates(result.evaluation)
    _print_findings(result.report.findings, "layout")
    log.info("wrote %s", output)
    console.print(f"[green]wrote[/] {output}")
    if not result.report.ok:
        raise typer.Exit(code=1)
