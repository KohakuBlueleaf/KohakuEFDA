---
title: Internals
summary: The package map and the path of one run through plan, netlist, layout and verification, with the files that carry each step.
tags:
  - dev
  - internals
---

# Internals

Read with `src/kohakuefda/` open. Concept pages explain why; this page says where.

## Packages

| Package | Holds |
|---|---|
| `model/` | Pydantic models with exact `Fraction` rates: items, machines, recipes, logistics, basements, dataset, scenario, plan, layout, cells and netlist, placement. No logic beyond lookups and load/save. |
| `data/` | The manifest client, table fetch with a SHA manifest, the mirror, wiki names, the normalisers that build `Dataset`, the update classifier, the IndustrialPlanner importer. |
| `flow/` | Lane sizing, plan nets, stability findings, the evaluation schema. |
| `plan/` | Recipe graph, the HiGHS model, the planner, outcomes, alternatives, zone membership, one cell per machine, the netlist, depot access arithmetic. |
| `layout/` | The board, the stage's settings and solver table, the project's lane router, the stages, the pipeline. |
| `physics/` | The Endfield pack for KohakuLayout: fabric, library, carriers, fields, boundaries, flow, rules, objective and the facts the pack reads from `attrs`. |
| `synth/` | The project netlist as a framework problem, the framework layout back as placement and layout, a project layout from any source as a framework problem and layout, the blueprint modules, the studio's frames. |
| `verify/` | The checks and the evaluation over the framework, the rate rule, the report. |
| `render/` | Rich tables, the text grid, the PNG. |
| `cli/` | Typer commands. |
| `serve/` | The web app's server, API and run manager. |
| `i18n/` | CLI strings per language. |

## One run

### Plan

`plan/recipes.py` expands the targets (`expand`) under `allowed`. `plan/lp.py` builds and solves the HiGHS model (`solve`) and snaps the result. `plan/planner.py` turns it into `RecipeUse` records, rebuilds exact balances, adds dump units, computes the power draw and footprint, collects findings from `flow/stability.py`, builds nets with `flow/nets.py` and returns a `Plan`.

### Netlist

`plan/machines.py` instantiates cells: `recipe_cell` builds one machine with a pin per lane on the ports the recipe binds (`lane_pins`), `zone_cell` a Gas Dispersing Unit heading a group whose members `plan/zones.py` picks (`assign_zones`), `entry_cell` an outside input, `core_cell` the Automation-Core with its depot ports or `parked_core` without, `bus_part` a Depot Bus Port or Section and `brick_cell` a Depot Loader or Unloader (free in the `bus` group in Wuling, bound to a slot in Valley IV), `dump_cell` a Water Treatment Unit; `CellFactory.depot` hands solid lanes to the core when asked, then to bricks with the sections `layout/depot_via.py` counts (`chain_capacity`, `sections_needed`, `io_budget`). `plan/netlist.py` collects pins into one `NetSpec` per item with findings. `plan/alternatives.py` re-plans with each rival recipe (`alternatives`) and lists the machines a ban still leaves feasible (`bannable`).

### Layout

`layout/stages.py` builds the basement board, turns the netlist into a framework problem with `synth/problem.py`, runs `kohakulayout.pipeline.solve` with the solver `layout/settings.py` names for the flat settings, and translates the framework layout back with `synth/layout.py`. `synth/frames.py` turns the framework's frames into the studio's. See the [KohakuLayout pages](../kohakulayout/README.md).

### Routing

The framework's router places every wire under the pack's carriers and rules. `synth/flows.py` reads the flows along each wire from the lane facts, and `synth/layout.py` cuts the wire into segments at its junctions, choosing each junction's splitter or converger and rotation from the flows meeting there.

### Verification

`synth/reverse.py` reads the project layout back as a framework problem and layout from its geometry alone: every machine a cell with its footprint and flow facts, every logistics unit a unit, every segment matched to the ports it leaves from and arrives at. `verify/layout.py` (`check_layout`) loads it into a world and runs KohakuLayout's verify runner under the pack: the framework's structural, occupancy, legality and coverage findings, then the pack's deck. `verify/evaluate.py` (`evaluate`) runs the framework's routed evaluator over it under the pack's flow hooks and reads the result back as the project's `Evaluation`; `verify/rules/rates.py` compares it with the plan. `verify/report.py` collects findings.

### Rendering and serving

`render/tables.py`, `render/grid_text.py`, `render/png.py` draw; `serve/` runs stages for the web app and `cli/view.py` starts it with `web_dist/`.

## Conventions that shape the code

- Rates are `Fraction`s per minute everywhere; floats only at the solver boundary and in renderers.
- Registries and data tables over branching: sources, sinks, unit kinds and rule ids are dictionaries, not `if` chains.
- Every knob a stage reads is a module-level constant or a stage parameter (`LAYOUT_DEFAULTS`, `ILLEGAL`, `SNAP_DENOMINATOR`), so behaviour is configured, not patched.
- Every stochastic routine takes a seed.
- Library code logs; it never prints.
