---
title: Testing
summary: The flat pytest suite, its fixtures and benchmark scenarios, the engine tests on hand-built netlists, the docs gate, and the check commands.
tags:
  - dev
  - testing
---

# Testing

`tests/` is flat: one file per subject, behaviour assertions on real collaborators, and one seam only, the external data source, which is recorded under `tests/fixtures/`. There is no coverage gate and no file-size guard.

## Files

| File | Pins |
|---|---|
| `test_smoke.py` | Version string, the CLI's command list. |
| `test_rates.py`, `test_geometry.py`, `test_ports.py`, `test_names.py` | Exact rates, rotations, the port mapping rule against Refining Unit and Reactor Crucible, name fallbacks. |
| `test_dataset_facts.py`, `test_glossary_coverage.py`, `test_check.py` | Facts of the pinned dataset, trilingual name coverage, the update classifier. |
| `test_scenario.py`, `test_planner.py` | The TOML loader; machine counts, sinks, degrade, region and gas filters, expansion. |
| `test_layout.py`, `test_importer.py` | Hand-built lines: connectivity, rules, evaluation, splitters, conduits, dumps, direct links; the IndustrialPlanner importer on a small fixture and the `check` command. |
| `test_engine.py` | The engine on hand-built netlists: wired machines end close, routed and powered; the parked core stands inside the area and counts; outside inputs on the border feed a zone; a laid bus seats its bricks and stays one cluster; Valley IV bricks take slots; the core's ports carry supply and delivery; the greedy cover; the line is solid and cannot be pulled closer to the corner; cancellation and a budget that cannot run; the area, entry and bus rules on hand-built layouts. |
| `test_netlist.py` | The three benchmarks' netlists carry the plan's rates with one machine per cell; Wuling solids through bus parts and bricks in the `bus` group; the chain arithmetic and lane packing; fluids at the border and zones as groups; the core parked unless asked; Valley IV bricks bound to slots; the `netlist` command. |
| `test_alternatives.py` | Rival recipes give other feasible plans; a banned machine never appears and the bannable list keeps the targets feasible. |
| `test_place_route.py` | A diagonal crossing gets a bridge and delivers; the three benchmarks lay out clean and at the plan's rates inside their area with the core placed and modules within blueprint limits; the `layout` command writes its artifacts. |
| `test_view.py` | The server's static side: artifact index, files, dataset, bundle, and refusal of paths outside the directory. |
| `test_plan_sanity.py` | Plans a player would build, on two recorded player scenarios and small lines: whole machines, conserved items, the crucible chosen over a transmuter chain, activation per built machine, Carbon from the plot loop and never from Wood, sewage treated rather than bottled into the depot, liquid and machine bans, the power draw reported. |
| `test_item_names.py` | Filled containers carry their contents in the name, so every item a recipe uses has its own name in every language. |
| `test_stages.py` | The staged pipeline: parameter defaults and casting, the layout stage's frames and checkpoint, verification, reproducibility per seed, cancellation. |
| `test_api.py` | The run API over HTTP: metadata, examples, scenario TOML round trip, a run driven stage by stage with parameters, artifacts, frames and events, rerunning the layout with other settings (later stages cleared), cancelling a running layout, bad input. |
| `test_docs.py` | Every docs page has front matter and one H1, every relative link resolves, and the site configuration lists only existing pages. |
| `test_wiki_recipes.py` | Every crafting recipe of the wiki's recipe modules (recorded in `fixtures/wiki_recipes.json`) is in the dataset with the same facility, stacks, time and environment; every dataset recipe is on the wiki unless it is an event recipe. |
| `test_game_facts.py` | Mechanics pinned against the wiki and the community calculators: pylon and core footprints and ports, the Planting Unit's recipes and the plots it does not need, activation and zone rates, dump and source rates. |
| `test_plan_paths.py` | The least-machine path under constraints: a crucible over a transmuter chain, gas off keeps liquid lines makeable and never marks their products as hand-gathered, ores feed their own refiners, allowing gas never costs more, natural resources offered by default, event recipes excluded. |
| `test_layout_goals.py` | What a placed line must satisfy: one machine per cell, the core placed, pylons covering the line, rotation free per machine, fluids from outside and everything inside the area, and the 15/min Hetonite line inside its 40×40 square. |

## Benchmarks

Three scenarios under `tests/fixtures/` exercise the whole pipeline: `scenario_valley_battery.toml` (LC Valley Battery, solids only, Infra-Station level 2), `scenario_wuling_hetonite.toml` (Hetonite with crucibles, a Purification Unit, refiners, shredders, Water Treatment Units and water from outside, Sky King Flats level 3) and `scenario_gas_xiranite.toml` (Xiranite in a stable-gas zone with the gas from outside, Sky King Flats level 2). `scenario_basic.toml` is the 15/min Hetonite line in Sky King Flats level 2.

## Checks

```bash
black .
ruff check .
python scripts/dev/comment_budget.py src scripts tests
pytest -q
```

and for the viewer, in `src/kohakuefda-viewer/`:

```bash
npm run format:check
npm run lint
npm test
npm run build
```

`npm test` runs vitest over the pure modules: `graph.test.js` (cycle-safe layering of the plan graph), `graph.layout.test.js` (one cell per node), `graph.crossing.test.js` (a recorded player's plan: supply nodes beside their consumers, no routed edge through a node, one cell per node and dummy), `graph.route.test.js` (an unavoidable crossing drawn once with a hop, parallel edges on separate tracks, a dummy in the middle column of a long edge, back edges under the graph, label anchors) and `drafts.test.js` (settings drafts survive stage events and reset on request).

`python scripts/dev/wiki_recipes.py fetch` re-records the wiki's recipe modules into `tests/fixtures/wiki_recipes.json`; `python scripts/dev/wiki_recipes.py diff` prints every difference against the dataset.

`comment_budget.py` enforces the comment rules: inline comment runs of at most two lines, docstrings of at most fourteen, no history or editorial comments, with `# justify: <reason>` as the escape hatch.
