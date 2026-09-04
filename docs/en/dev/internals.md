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
| `layout/` | World geometry and connectivity, fragments, depot access and bus arithmetic, the pylon cover, blocks, the board, the group rules, the live site where machines and their wires share one grid, the spread that lays a whole layout at once, the shrink that squeezes it, the genome and the searches over it, the engine, assembly, chunking, the stages, the pipeline. |
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

`layout/stages.py` reads the basement's geometry (`layout/board.py`: square, ring, fixed bus cells, slots) and runs `layout/engine.py`. `layout/place.py` holds `Block` (anchor, rotation, chosen ports, group, world pins, footprint cells). `layout/floorplan.py` holds the genome, the envelope packing (`Floorplan.pack`), the gaps and margins with their channels (`channel_at`, `channels_around`, `widen`), the group faults (`bus_faults`, `zone_faults`), the moves (`Moves`) and the seed (`seed`, `bus_seed`, `zone_seed`). `layout/search.py` holds the optimisers (`anneal`, `lns`, `genetic`, `greedy`) over one `evaluate`. `Engine.run` searches and details the kept genomes; `Engine.detail` packs, seats bricks (`place_bricks`) and outside inputs (`place_entries`), covers with pylons (`layout/coverage.py`), assembles (`layout/assemble.py`), routes (`route/router.py`), widens, and `Engine.finish` emits the wires, compacts (`layout/compact.py`), chunks (`layout/chunk.py`), measures and checks.

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
