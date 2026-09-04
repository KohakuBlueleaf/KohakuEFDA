---
title: Dependency graph
summary: The import order between packages and the modules that sit across package lines.
tags:
  - dev
  - internals
  - architecture
---

# Dependency graph

Imports flow one way, from leaves to the CLI. The order is by module, and a few modules of one package sit above modules of a later package, which the tiers below make explicit.

```
  cli/, serve/                                  commands, the run API
  render/, layout/pipeline.py                   tables, grids, the PNG, the whole run
  layout/stages.py                              the four stages
  layout/engine.py                              rounds, pylons, measurement, checks
  layout/genome.py                              the decisions a layout is made of
  layout/search.py                              restart, anneal and evolve over the genome
  layout/spread.py                              the lattice that lays a whole layout at once
  layout/shrink.py                              carve, press and nudge, whole layout to whole layout
  layout/site.py                                machines and their wires on one grid
  layout/groups.py, board.py
  route/router.py                               wires, trunks, crossings, rip-up
  layout/place.py, assemble.py, chunk.py
  plan/machines.py, zones.py, netlist.py, alternatives.py
  verify/rules/, flow/evaluate.py               rules and the evaluator
  route/grid.py, route/pathfinder.py            occupancy and search
  layout/geometry.py, connect.py, fragments.py, depot_via.py, coverage.py
  plan/recipes.py, lp.py, planner.py, outcomes.py, flow/lanes.py, nets.py, stability.py
  data/                                         tables in, dataset out
  model/                                        leaf
```

## The rules

- `model/` imports nothing from the project.
- `data/` imports `model/` only.
- `flow/lanes.py`, `flow/nets.py`, `flow/stability.py` and the planner import `model/` and each other, never geometry.
- `layout/geometry.py`, `layout/connect.py`, `layout/depot_via.py` and `layout/coverage.py` are pure world geometry over `model/`; `route/grid.py` builds occupancy from them.
- `verify/rules/geometry.py` and `flow/evaluate.py` need connectivity, occupancy, the bus constants and the zone geometry, so they sit above `layout/connect.py`, `layout/depot_via.py`, `layout/coverage.py` and `route/grid.py`.
- `plan/machines.py` needs lane sizing, the zone fit of `plan/zones.py` and the chain arithmetic of `layout/depot_via.py`; `plan/netlist.py` builds on it.
- `route/router.py` needs assembled pins and the occupancy grid.
- `layout/groups.py` needs blocks, the zone geometry and the bus constants; `layout/site.py` needs the groups, the board, assembled pins and the router, and is the only place a machine is placed or a wire routed. `layout/genome.py` imports nothing of the project and `layout/search.py` needs only the genome, so a search knows nothing about geometry; `layout/spread.py` needs the site, the genome and the searches; `layout/shrink.py` needs the site and the spread; `layout/engine.py` needs the spread, the shrink, the chunker and the geometry rules; `layout/stages.py` drives the engine.
- `layout/pipeline.py`, `serve/` and `cli/` are the top: they import every stage they drive.

The package `README.md` files list each package's dependencies; a change that adds an import against this order should change the list and this page in the same commit.
