---
title: Importing blueprints
summary: Read an IndustrialPlanner blueprint as a layout, what the importer recovers, and where it has to guess.
tags:
  - guides
  - import
  - industrialplanner
---

# Importing blueprints

IndustrialPlanner is a community web editor for AIC layouts. Its blueprints (schema version 5) can be checked and rendered by KohakuEFDA directly; `check` and `render` detect the format by its `schemaVersion` and `entities` keys and import it on the fly.

```bash
kohakuefda check  getting-started-tutorial.json
kohakuefda render getting-started-tutorial.json
```

## What is recovered

- **Machines** by their game definition id. IndustrialPlanner stores machines in its registry's default orientation, which is our rotation plus 180 degrees for most machines and plus 0 for the Depot Loader and Unloader; the importer applies that per definition.
- **Belts and pipes** from one entity per cell with a heading: the importer chains straight and turn tiles into segments and keeps the heading of single-cell chains.
- **Locked items**: a Depot Unloader's or Conduit Inlet's storage lock becomes the entity's item.
- **Recipes**: IndustrialPlanner names recipes by its own slugs (`r_<machine>_<outputs>_from_<inputs>_<mode>`). The importer scores every recipe of that machine by the overlap between the slug's words and the item ids of the recipe's inputs and outputs, and keeps the best above a floor. A machine with several recipe channels keeps the channel whose outputs match the port accept rules in the blueprint, else the first.
- **Pumps**: the pump slug names the fluid, matched the same way among items of the pump's phase.
- **Conduit links**: `slotLinks` between a Conduit Outlet and a Conduit Inlet.
- **Positions**: blueprints may use negative coordinates; the result is shifted into a box with a one-cell margin.

## Limits

- A Reactor Crucible running two channels in IndustrialPlanner (one recipe feeding another inside the machine) is imported with one recipe, so its internal chaining does not evaluate; the rate table shows it stalled on the input the other channel would have made.
- IndustrialPlanner's `chrono` recipe variants have no verified counterpart in the game tables; they match by word overlap like every other slug.
- The blueprint's `baseId` becomes the basement id; the level and depot level default to 1 because the blueprint does not carry them.

The importer lives in `src/kohakuefda/data/importers/industrial_planner.py`; the test fixture `tests/fixtures/industrial_planner_min.json` is a small blueprint that exercises every branch.
