# Bench

Layout portfolios over the real pipeline: every case × transport × solver × seed,
each trial in its own process under a hard wall-time ceiling.

## Files

| File | Description |
|---|---|
| `run.py` | `run` (the grid, a manifest, matched inputs per case and transport, bounded concurrent workers, `summary.json` with the ledger, reliability and winners, then `report`), `worker` (one trial through `layout_stage`; the first routed, best and diagnostic layouts each with terms, geometry findings, complexity and the routed evaluation from both initial states), `report` (`report.html`: the ledger and every winner's text map) |

## Running

Run it with the repository's `.venv` interpreter: `.venv/Scripts/python.exe
scripts/dev/bench/run.py run --help` lists the case (a fixture stem after `scenario_`),
transport, solver, seed, time, action, worker, backend, output and options arguments.
Options are a JSON object keyed by solver name. The output directory must not exist;
evidence is never overwritten. Workers fix the Python hash seed and run numeric
libraries on one thread.

A trial is verified when every cell is placed, the best layout has no geometry error,
and its routed evaluation from the declared initial state converges without a rate
error. The empty-state check is recorded beside it; a declared steady state is a
primed one, not a cold start.

## Dependencies

- The project's stages, dataset, verify and render modules; `typer`.
