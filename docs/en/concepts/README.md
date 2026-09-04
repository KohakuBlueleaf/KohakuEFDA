---
title: Concepts
summary: Mental models for the factory, the pipeline, planning, rows and netlists, placement and routing, and verification.
tags:
  - concepts
  - overview
---

# Concepts

Concept pages explain why each stage is shaped the way it is. They are not field lists (those are in [Reference](../reference/README.md)) and not task recipes (those are in [Guides](../guides/README.md)). Read them when you want the tool's decisions to feel obvious rather than arbitrary.

## Reading paths

### Understanding a plan (20 minutes)

1. [Why KohakuEFDA](foundations/why-kohakuefda.md)
2. [The factory model](foundations/the-factory-model.md)
3. [The pipeline](foundations/the-pipeline.md)
4. [Planning](planning/README.md): recipe graph, solver, lanes and stability

### Understanding a layout (one hour)

1. The path above
2. [Machines](cells/machines.md): one machine per cell, its pins, and the cells that touch the outside
3. [Netlist](cells/netlist.md): how a plan becomes rows and nets
4. [Blocks and placement](layout/blocks-and-placement.md)
5. [Routing](layout/routing.md)
6. [Steady state](verification/steady-state.md): how a layout is proven to run at its rates

### Checking someone else's layout

1. [The factory model](foundations/the-factory-model.md)
2. [Geometry rules](verification/geometry-rules.md)
3. [Steady state](verification/steady-state.md)

## Sections

- [Foundations](foundations/README.md): the problem, the model, the stages.
- [Planning](planning/README.md): what runs, on how many machines, through how many lanes.
- [Cells and netlists](cells/README.md): one cell per machine, the core, bus parts, bricks, outside inputs and zone units bound into groups, and the netlist.
- [Placement and routing](layout/README.md): blocks, the engine with the router in the loop, pylons, the router, modules.
- [Verification](verification/README.md): geometry rules and the evaluator.
- [Glossary](glossary.md): every term, with the game's names in three languages.
