"""``kohakuefda plan``: plan a scenario and print the report."""

import logging
from pathlib import Path

import typer
from rich.console import Console

from kohakuefda.cli.data import DEFAULT_ROOT, load_dataset
from kohakuefda.model.scenario import Scenario
from kohakuefda.plan.planner import plan as plan_scenario
from kohakuefda.render.tables import plan_report

log = logging.getLogger(__name__)
console = Console()


def plan_cmd(
    scenario_file: Path = typer.Argument(..., help="scenario.toml"),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Write plan.json here."
    ),
    version: str = typer.Option("", "--version", "-v", help="Dataset version id."),
    root: Path = typer.Option(DEFAULT_ROOT, "--root"),
    lang: str = typer.Option("en", "--lang", help="en | zh-TW | zh-CN"),
) -> None:
    """Plan recipes, machine counts, lanes and stability for a scenario."""
    log.info("planning %s against dataset %s", scenario_file, version or "newest")
    dataset = load_dataset(root, version)
    scenario = Scenario.from_toml(scenario_file)
    result = plan_scenario(dataset, scenario)
    log.info(
        "plan %s: %d machines, scale %s",
        result.status,
        result.machine_count,
        result.scale,
    )
    console.print(plan_report(result, dataset, lang))
    if output is not None:
        result.save(output)
        log.info("wrote %s", output)
        console.print(f"[green]wrote[/] {output}")
    if result.status == "infeasible":
        raise typer.Exit(code=1)
