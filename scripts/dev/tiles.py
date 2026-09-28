"""Lay out every repeat unit of a scenario once and record what came out: a text map, the
macro's footprint and ports, and the tile's build complexity, into a run directory."""

import json
import logging
import resource
import time
from pathlib import Path

import typer

from kohakuefda.layout.tiles import TileError, cost_of, lay_out_tile, text_map
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.scenario import Scenario
from kohakuefda.plan.netlist import build_netlist
from kohakuefda.plan.planner import plan
from kohakuefda.synth import problem_of
from kohakuefda.synth.hierarchy import hierarchical_of
from kohakuefda.verify.complexity import complexity_text

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "data" / "1.5.3@9764758-3" / "dataset.json"
FIXTURES = ROOT / "tests" / "fixtures"
CASES = "dense_valley18,dense_wuling6"
OUTPUT = ROOT / "out" / "tiles"
UNITS = 6000
SEEDS = "0,1,2,3"
app = typer.Typer(add_completion=False)


@app.command()
def main(
    cases: str = CASES,
    output: Path = OUTPUT,
    units: int = UNITS,
    seeds: str = SEEDS,
) -> None:
    """Lay out the tiles of each case and write maps, macros and a summary."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    dataset = Dataset.load(DATASET)
    seed_list = tuple(int(s) for s in seeds.split(","))
    summary: list[dict] = []
    for case in cases.split(","):
        scenario = Scenario.from_toml(FIXTURES / f"scenario_{case}.toml")
        netlist = build_netlist(dataset, scenario, plan(dataset, scenario))
        hier = hierarchical_of(netlist, problem_of(dataset, netlist).netlist)
        directory = output / case
        directory.mkdir(parents=True, exist_ok=True)
        for module_id in sorted(hier.modules):
            copies = sum(1 for c in hier.cells.values() if c.module == module_id)
            started = time.monotonic()
            try:
                result = lay_out_tile(hier, module_id, seed_list, units)
            except TileError as failure:
                summary.append(
                    {
                        "case": case,
                        "module": module_id,
                        "copies": copies,
                        "error": str(failure),
                    }
                )
                peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024
                typer.echo(
                    f"{case} {module_id} x{copies}: FAILED {failure} peak={peak}MB"
                )
                continue
            elapsed = time.monotonic() - started
            found = result.complexity
            footprint = result.macro.footprint
            row = {
                "case": case,
                "module": module_id,
                "copies": copies,
                "cells": len(result.problem.netlist.cells),
                "footprint": [footprint.width, footprint.height],
                "ports": [(p.id, p.side, p.offset) for p in footprint.ports],
                "cost": str(cost_of(result.assessment)),
                "seconds": round(elapsed, 1),
                "complexity": found.model_dump(mode="json"),
            }
            summary.append(row)
            (directory / f"{module_id}.txt").write_text(
                text_map(result.problem, result.macro.layout, footprint) + "\n",
                encoding="utf-8",
            )
            (directory / f"{module_id}.macro.json").write_text(
                result.macro.model_dump_json(indent=1), encoding="utf-8"
            )
            peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024
            typer.echo(
                f"{case} {module_id} x{copies}: {footprint.width}x{footprint.height} "
                f"cost={row['cost']} {elapsed:.1f}s peak={peak}MB {complexity_text(found)}"
            )
    (output / "summary.json").write_text(
        json.dumps(summary, indent=1), encoding="utf-8"
    )


if __name__ == "__main__":
    app()
