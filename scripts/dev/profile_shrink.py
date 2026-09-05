"""Measure baseline compaction separately from construction and rate verification."""

import cProfile
import json
import pstats
import time
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path

import typer

from kohakuefda.framework import problem_of
from kohakuefda.framework.checkpoint import save_snapshot
from kohakuefda.framework.runtime import Runner
from kohakuefda.model.cells import Netlist
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.plan import Plan
from kohakuefda.model.scenario import Scenario
from kohakuefda.plan.netlist import build_netlist
from kohakuefda.plan.planner import plan
from kohakuefda.solvers.baseline import Baseline
from kohakuefda.solvers.baseline.shrink import Shrink
from kohakuefda.util.logging import setup

DATASET = Path("data/1.5.3@9764758-3/dataset.json")
SCENARIO = Path("tests/fixtures/scenario_hub_battery.toml")
OUTPUT = Path("out/shrink-profile")
SEED = 0
ROUNDS = 200
ATTEMPTS = 64
REPEATS = 1
BACKEND = "native"
PROFILE = False
TOP = 35
SCREEN = True
DEDUPLICATE = True


class Measurements:
    """Collect attempted work per accepted shrink round and the terminal failed scan."""

    def __init__(self) -> None:
        self.started = time.monotonic()
        self.last = self.started
        self.counts = Counter()
        self.durations = defaultdict(float)
        self.round_counts = Counter()
        self.rounds = []
        self.accepted = []

    def observe(self, event) -> None:
        payload = json.loads(event.payload_json)
        if event.kind == "attempt":
            key = f"{payload['action']}:{payload['outcome']}"
            self.counts[key] += 1
            self.round_counts[key] += 1
            self.durations[key] += event.duration
        elif event.kind == "accepted":
            self.accepted.append(
                {"id": payload["state_id"], "metrics": payload["metrics"]}
            )
        elif event.kind == "improve":
            self.finish_round(payload["step"])

    def finish_round(self, step: int | None) -> None:
        now = time.monotonic()
        self.rounds.append(
            {
                "step": step,
                "seconds": now - self.last,
                "attempts": dict(self.round_counts),
            }
        )
        self.round_counts.clear()
        self.last = now


def main(
    output: Path = OUTPUT,
    scenario: Path = SCENARIO,
    dataset_path: Path = DATASET,
    run_dir: Path | None = None,
    backend: str = BACKEND,
    seed: int = SEED,
    rounds: int = ROUNDS,
    attempts: int = ATTEMPTS,
    repeats: int = REPEATS,
    profile: bool = PROFILE,
    screen: bool = SCREEN,
    deduplicate: bool = DEDUPLICATE,
) -> None:
    """Run identical seeded shrink trials; optionally collect cProfile with its timing overhead."""
    if repeats < 1 or rounds < 0:
        raise typer.BadParameter("repeats must be positive and rounds nonnegative")
    setup("WARNING")
    dataset = Dataset.load(dataset_path)
    if run_dir is None:
        requested = Scenario.from_toml(scenario)
        planned = plan(dataset, requested)
        netlist = build_netlist(dataset, requested, planned)
    else:
        planned = Plan.load(run_dir / "plan.json")
        netlist = Netlist.load(run_dir / "netlist.json")
    problem = problem_of(dataset, netlist, planned)
    settings = {"backend": backend, "seed": seed, "check_rates": False}
    builder = Baseline(spread_attempts=attempts, shrink_rounds=0)
    construction = Runner(problem, settings=settings).run(builder)
    initial = construction.current
    if initial is None or not initial.assessment.routed:
        raise RuntimeError("construction did not yield a routed seed")
    output.mkdir(parents=True, exist_ok=True)
    save_snapshot(initial, output / "initial.json")
    rows = []
    for repeat in range(repeats):
        runner = Runner(problem, settings=settings)
        ctx = runner.context
        ctx.import_snapshot(initial)
        ctx.budget.work.clear()
        measurements = Measurements()
        ctx.observe = measurements.observe
        profiler = cProfile.Profile()
        if profile:
            profiler.enable()
        Shrink(
            ctx,
            tuple(builder.spread.order),
            rounds,
            screen_candidates=screen,
            deduplicate=deduplicate,
        ).run()
        if profile:
            profiler.disable()
        elapsed = time.monotonic() - measurements.started
        measurements.finish_round(None)
        snapshot = ctx.current
        row = {
            "repeat": repeat,
            "profiled": profile,
            "screen": screen,
            "deduplicate": deduplicate,
            "seconds": elapsed,
            "initial": initial.id,
            "final": snapshot.id,
            "assessment": asdict(snapshot.assessment),
            "work": dict(ctx.budget.work),
            "attempts": dict(measurements.counts),
            "attempt_seconds": dict(measurements.durations),
            "rounds": measurements.rounds,
            "accepted": measurements.accepted,
        }
        if profile:
            profiler.dump_stats(str(output / f"shrink-{repeat}.prof"))
            stats = pstats.Stats(profiler)
            for sort in ("cumulative", "tottime"):
                with (output / f"{sort}-{repeat}.txt").open(
                    "w", encoding="utf-8"
                ) as stream:
                    stats.stream = stream
                    stats.sort_stats(sort).print_stats(TOP)
        save_snapshot(snapshot, output / f"final-{repeat}.json")
        rows.append(row)
        summary = {
            "problem": problem.id,
            "source": str(run_dir or scenario),
            "settings": json.loads(construction.settings_json),
            "construction_seconds": construction.elapsed,
            "spread_attempts": builder.spread.tried,
            "runs": rows,
        }
        (output / "summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    "seconds": elapsed,
                    "profiled": profile,
                    "work": row["work"],
                    "attempts": row["attempts"],
                    "metrics": dict(snapshot.assessment.metrics),
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    typer.run(main)
