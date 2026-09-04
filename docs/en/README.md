---
title: KohakuEFDA Documentation
summary: Home for the factory model, the pipeline, the guides, the reference and the development notes.
tags:
  - overview
  - docs
---

# KohakuEFDA Documentation

KohakuEFDA ("End Field Design Automation") plans and lays out factories for the Automated Industry Complex (AIC) in *Arknights: Endfield*. It reads only static game data and never touches the game; the output is a verified build plan you reproduce by hand.

You give it four things: the rates at which raw materials arrive, the products and rates you want, the basement you build in (its region, which Core AIC Area, its level and its depot level), and a mode that says whether area or machine count matters more. Everything else is decided by the tool: which recipes run and on how many machines, how many belts and pipes each flow needs, where every machine, the Automation-Core, the Depot Bus and its bricks, the pylons and the outside inputs go, how every belt and pipe is routed, and whether the result obeys the rules the game enforces.

The work happens in stages, each writing a JSON artifact the next one reads: a **plan** (recipes, machine counts, item balances, nets), a **netlist** (one cell per machine with its pins and groups, and the nets between pins), a **placement** and a **layout** (every machine, logistics unit, belt, pipe and outside input on the grid), an **evaluation** (the steady-state rate on every segment and machine) and a **report** (every rule finding). A web app runs the stages one at a time, with tunable parameters, live frames of the layout search and its detailed pass, and reruns from any checkpoint, and shows every artifact.

## Pick a path

| You are... | Start here |
|---|---|
| **Trying it on your own factory** | [Getting started](guides/getting-started.md) · [First plan](tutorials/first-plan.md) · [Scenarios](guides/scenarios.md) |
| **Checking a layout you built or imported** | [Checking layouts](guides/checking-layouts.md) · [Importing blueprints](guides/importing-blueprints.md) · [Geometry rules](concepts/verification/geometry-rules.md) |
| **Reading the results** | [The pipeline](concepts/foundations/the-pipeline.md) · [Artifacts](reference/artifacts.md) · [Studio](guides/viewer.md) |
| **Understanding the model** | [The factory model](concepts/foundations/the-factory-model.md) · [Planning](concepts/planning/README.md) · [Cells](concepts/cells/README.md) · [Layout](concepts/layout/README.md) |
| **Contributing** | [Development](dev/README.md) · [Internals](dev/internals.md) · [Testing](dev/testing.md) · [Assumptions](dev/assumptions.md) |

## Documentation structure

### Tutorials

Guided walks that end with something on your screen.

- [First plan](tutorials/first-plan.md): a scenario file, the planner, and how to read its tables.
- [First layout](tutorials/first-layout.md): the same scenario placed, routed, checked, rendered and opened in the viewer.

### Guides

Task-oriented: "how do I do X".

- [Getting started](guides/getting-started.md): install, fetch the dataset, run every command once.
- [Scenarios](guides/scenarios.md): the scenario file field by field, and what happens when a target cannot be met.
- [Checking layouts](guides/checking-layouts.md): the layout file format, the rule report, the rate table, text and PNG renders.
- [Importing blueprints](guides/importing-blueprints.md): IndustrialPlanner blueprints as layouts, and what the importer can and cannot recover.
- [Studio](guides/viewer.md): designing a line in the browser from pictures and names, building it stage by stage, watching the layout search and its detailed pass, growing it from its outcomes, and what each page shows.
- [Dataset updates](guides/dataset-updates.md): pinning a game version, comparing versions, and telling a safe update from one that needs code.

### Concepts

Mental models: why the tool is shaped the way it is. Field lists live in the reference.

- [Overview](concepts/README.md)
- [Foundations](concepts/foundations/README.md): why the project exists, the factory as the tool models it, and the pipeline.
- [Planning](concepts/planning/README.md): recipe graph, the solver, lanes and stability.
- [Cells and netlists](concepts/cells/README.md): one cell per machine with its ports as pins, the core, bus parts, bricks, outside inputs and zone units in their groups, and how a plan becomes cells and nets.
- [Layout](concepts/layout/README.md): blocks and groups, placing and routing as one operation, the lattice spread and the shrink, the searches over them, pylons, the router, blueprint modules.
- [Verification](concepts/verification/README.md): geometry rules and the steady-state evaluator.
- [Glossary](concepts/glossary.md): every project-specific term, with the game's own names in three languages.

### Reference

Exhaustive lookup.

- [CLI](reference/cli.md): every command and flag.
- [Scenario file](reference/scenario-file.md): every field of `scenario.toml`.
- [Artifacts](reference/artifacts.md): the shape of every JSON file the tool writes.
- [Rules](reference/rules.md): every finding id, its severity and what it means.
- [Dataset](reference/dataset.md): the normalised dataset, its sources and its versioning.

### Development

For contributors.

- [Development home](dev/README.md)
- [Internals](dev/internals.md): package map and the flow through each stage.
- [Dependency graph](dev/dependency-graph.md): the one-way import order.
- [Testing](dev/testing.md): the flat test suite, the benchmarks, the check commands.
- [Frontend](dev/frontend.md): the web app's architecture, the run API and the event stream.
- [Assumptions](dev/assumptions.md): game mechanics the tool assumes and has not verified in play, and known limits.

## Codebase map

```
src/kohakuefda/
  data/       fetch and normalise the game tables; importers for community formats
  model/      typed domain objects: items, machines, recipes, basements, scenario, plan, layout, cells
  i18n/       UI strings for the CLI in en, zh-TW, zh-CN
  flow/       lane sizing, nets, stability findings, the steady-state evaluator
  plan/       recipe graph, the HiGHS solver, the planner, alternatives, cells and netlists
  layout/     geometry, connectivity, bus arithmetic, blocks, pylon cover, group rules, the site, the builder, the engine, assembly, chunking, stages, pipeline
  route/      occupancy grid, pathfinder, router
  verify/     geometry and rate rules, the report
  render/     rich tables, text grid, PNG
  cli/        the kohakuefda command
  web_dist/   the built viewer (output of npm run build)

src/kohakuefda-viewer/   Vue 3 viewer
data/<versionId>/        normalised dataset, versioned by game hotfix
tests/                   flat pytest suite and its fixtures
docs/                    this tree
```

Every subpackage has a `README.md` listing its files and dependencies; those are the most accurate description of what lives where.

## What the docs promise

- **Tutorials** get you to a result.
- **Guides** tell you how to do X.
- **Concepts** tell you why X works that way.
- **Reference** lists every X.

Numbers that describe one factory on one basement belong to that factory. Belt and pipe throughput, footprints and port positions come from the game data and are quoted as facts; anything measured on a benchmark scenario is labelled as such. If a page says "comprehensive", "powerful" or "seamless", it is out of date.
