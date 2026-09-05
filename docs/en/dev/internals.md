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
| `flow/` | Lane sizing, plan nets, stability findings, the steady-state evaluator. |
| `plan/` | Recipe graph, the HiGHS model, the planner, outcomes, alternatives, zone membership, one cell per machine, the netlist. |
| `layout/` | World geometry and connectivity, fragments, depot access and bus arithmetic, the pylon cover, blocks, the board, the group rules, the live site where machines and their wires share one grid, the stage engine adapter, assembly, chunking, the stages, the pipeline. |
| `framework/` | Immutable queries, transactions, snapshots, assessment, budgets and isolated execution; imports no concrete solver. |
| `solvers/` | Registered strategies; baseline owns seeded spread retries and greedy shrink policy. |
| `route/` | The occupancy grid, the A* pathfinder, the router. |
| `verify/` | Geometry rules, rate rules, the report. |
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

`layout/stages.py` builds the basement board and runs `layout/engine.py`. `layout/place.py` holds blocks and world pins; `layout/site.py` owns their shared routing grid and transactional placement. `solvers/baseline/spread.py` retries seeded flow orders and lattice gaps until a complete spread is found. `solvers/baseline/parallel.py` defines attempt slices and selects a worker snapshot; framework execution launches and cleans up the jobs. `solvers/baseline/shrink.py` proposes carve/press/nudge actions. Context owns rollback/publication, while framework assessment assembles, emits, measures and checks candidates. See the [framework reference](../framework/reference.md).

### Routing

`route/router.py` decomposes nets into wires (`wires_of`, `assign`), routes them with `route/pathfinder.py` (`RouteGrid`, `astar`) under negotiated congestion (`Router.route`), builds trunks for many-to-many pipe nets, then writes units and segments (`Router.emit`). `route/grid.py` provides the occupancy every check starts from.

### Verification

`verify/rules/geometry.py` (`check_layout`) runs every geometry rule over `route/grid.py`'s occupancy and `layout/connect.py`'s connectivity. `flow/evaluate.py` (`Evaluator`) relaxes the layout; `verify/rules/rates.py` compares it with the plan. `verify/report.py` collects findings.

### Rendering and serving

`render/tables.py`, `render/grid_text.py`, `render/png.py` draw; `serve/` runs stages for the web app and `cli/view.py` starts it with `web_dist/`.

## Conventions that shape the code

- Rates are `Fraction`s per minute everywhere; floats only at the solver boundary and in renderers.
- Registries and data tables over branching: sources, sinks, unit kinds and rule ids are dictionaries, not `if` chains.
- Every knob a stage reads is a module-level constant or a stage parameter (`LAYOUT_DEFAULTS`, `ILLEGAL`, `ROUTE_ROUNDS`, `SNAP_DENOMINATOR`), so behaviour is configured, not patched.
- Every stochastic routine takes a seed.
- Library code logs; it never prints.
