"""Rows of units on the bus: lay out a scenario's tiles once, fold the netlist onto their macros,
place the instances in rows with the floorplan, translate back and report the layout."""

import json
import logging
import time
from pathlib import Path

import typer

from kohakuefda.layout.settings import router_of
from kohakuefda.layout.tiles import lay_out_tiles
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.scenario import Scenario
from kohakuefda.plan.netlist import build_netlist
from kohakuefda.plan.planner import plan
from kohakuefda.plan.units import extract
from kohakuefda.render.grid_text import render_text
from kohakuefda.solvers import EndfieldFloorplan
from kohakuefda.synth import problem_of
from kohakuefda.synth.hierarchy import hierarchical_of, project_layout
from kohakuefda.synth.layout import layout_of
from kohakuefda.verify.complexity import complexity, complexity_text, with_units
from kohakuefda.verify.layout import check_layout
from kohakulayout.engine import Budget
from kohakulayout.pipeline import solve

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "data" / "1.5.3@9764758-3" / "dataset.json"
FIXTURES = ROOT / "tests" / "fixtures"
OUTPUT = ROOT / "out" / "rows"
UNITS = 20000
TILE_UNITS = 6000
app = typer.Typer(add_completion=False)


@app.command()
def main(
    case: str = "basic",
    output: Path = OUTPUT,
    units: int = UNITS,
    tile_units: int = TILE_UNITS,
    seed: int = 0,
    channel: int = 2,
    gap: int = 1,
) -> None:
    """Tiles, then rows of their instances; writes the layout, its map and its report."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    dataset = Dataset.load(DATASET)
    scenario = Scenario.from_toml(FIXTURES / f"scenario_{case}.toml")
    result = plan(dataset, scenario)
    netlist = build_netlist(dataset, scenario, result)
    flat = problem_of(dataset, netlist)
    hier = hierarchical_of(netlist, flat.netlist)
    started = time.monotonic()
    _, tiles = lay_out_tiles(hier, units=tile_units)
    typer.echo(f"{len(tiles)} tile(s) laid out in {time.monotonic() - started:.1f}s")
    macros = {m: r.macro for m, r in tiles.items()}
    problem = problem_of(dataset, netlist, macros=macros)
    typer.echo(
        f"hierarchical problem: {len(problem.netlist.cells)} top cells, {len(problem.netlist.nets)} top nets, check {problem.check()[:2]}"
    )
    started = time.monotonic()
    outcome = solve(
        problem,
        solver=EndfieldFloorplan.id,
        seed=seed,
        budget=Budget(units=units),
        params={"channel": channel, "gap": gap},
        router=router_of(),
        kernel="auto",
    )
    assessment = outcome.assessment
    typer.echo(
        f"rows: {outcome.outcome} in {time.monotonic() - started:.1f}s complete={assessment.complete} valid={assessment.valid} "
        f"placed={assessment.metrics.get('placed')} missing={assessment.metrics.get('missing')} unrouted={assessment.metrics.get('unrouted')} area={assessment.metrics.get('area')}"
    )
    if outcome.layout is None:
        raise typer.Exit(1)
    renamed = project_layout(outcome.layout, netlist, flat.netlist)
    _, layout = layout_of(flat, renamed, dataset, netlist, assessment)
    found = with_units(complexity(layout), extract(dataset, result))
    findings = check_layout(dataset, layout)
    errors = [f for f in findings if f.severity == "error"]
    typer.echo(f"report: {complexity_text(found)} errors={len(errors)}")
    for finding in errors[:8]:
        typer.echo(f"  {finding.rule}: {finding.message[:120]}")
    directory = output / case
    directory.mkdir(parents=True, exist_ok=True)
    layout.save(directory / "layout.json")
    (directory / "layout.txt").write_text(
        render_text(dataset, layout), encoding="utf-8"
    )
    (directory / "report.json").write_text(
        json.dumps(
            {
                "complexity": found.model_dump(mode="json"),
                "errors": len(errors),
                "metrics": {k: str(v) for k, v in assessment.metrics.items()},
            },
            indent=1,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    app()
