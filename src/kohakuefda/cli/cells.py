"""``kohakuefda netlist``: plan a scenario and print its cells and nets."""

import logging
from pathlib import Path

import typer
from rich.console import Console

from kohakuefda.cli.data import DEFAULT_ROOT, load_dataset
from kohakuefda.model.scenario import Scenario
from kohakuefda.plan.netlist import build_netlist
from kohakuefda.plan.planner import plan as plan_scenario
from kohakuefda.render.tables import netlist_report

log = logging.getLogger(__name__)
console = Console()


def netlist_cmd(
    scenario_file: Path = typer.Argument(..., help="scenario.toml"),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Write netlist.json here."
    ),
    version: str = typer.Option("", "--version", "-v"),
    root: Path = typer.Option(DEFAULT_ROOT, "--root"),
    lang: str = typer.Option("en", "--lang", help="en | zh-TW | zh-CN"),
) -> None:
    """Plan a scenario and turn it into cells and nets."""
    dataset = load_dataset(root, version)
    scenario = Scenario.from_toml(scenario_file)
    result = plan_scenario(dataset, scenario)
    netlist = build_netlist(dataset, scenario, result)
    log.info(
        "netlist: %d cells, %d nets, %d findings",
        len(netlist.cells),
        len(netlist.nets),
        len(netlist.findings),
    )
    console.print(netlist_report(netlist, dataset, lang))
    if output is not None:
        netlist.save(output)
        log.info("wrote %s", output)
        console.print(f"[green]wrote[/] {output}")
    if netlist.errors or result.status == "infeasible":
        raise typer.Exit(code=1)
