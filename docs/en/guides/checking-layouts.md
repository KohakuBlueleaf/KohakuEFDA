---
title: Checking layouts
summary: The layout file, the geometry rules, the steady-state rate table, and text or PNG renders of any layout.
tags:
  - guides
  - verify
  - render
---

# Checking layouts

`kohakuefda check` and `kohakuefda render` work on any layout file: one written by `kohakuefda layout`, one you edited, or one imported from an IndustrialPlanner blueprint ([Importing blueprints](importing-blueprints.md)).

## The layout file

A layout is a JSON file with a grid size, the basement it is for, and five lists:

- **machines**: id, machine id, anchor cell, rotation, mode, recipe, and a config (the item a Depot Unloader or pump emits, the item a Conduit Inlet accepts);
- **units**: 1×1 logistics units (splitters, convergers, bridges, control ports) with a rotation;
- **segments**: belts and pipes as ordered lists of cells from source to sink; a single-cell segment carries a heading; a segment may name the outside input it starts from;
- **entries**: outside inputs, each a border cell with the item and rate that enter there and the edge it enters from;
- **links**: conduit pairs (an inlet id and an outlet id).

Coordinates are grid cells, x to the right and y down, with a machine's anchor at its top-left cell and rotation clockwise in quarter turns. [Artifacts](../reference/artifacts.md#layoutjson) lists every field.

Two layers exist: the ground holds machines, belts and belt units; the sky holds pipes; pipe units and machines occupy both. A pipe may cross over a belt; nothing may cross a machine.

## check

```bash
kohakuefda check out/layout.json
kohakuefda check out/layout.json -o report.json
kohakuefda check out/layout.json --no-rates
```

The first table is the rule report: severity, rule id, subject and message for every geometry finding, with the error and warning counts in the title. The command exits with status 1 when any error is present, so it can gate a script. Every rule is explained in [Geometry rules](../concepts/verification/geometry-rules.md) and listed in [Rules](../reference/rules.md).

The second table is the rate table from the steady-state evaluator: every machine with its recipe, its utilisation as an exact fraction, and the cause when it is stalled ("no item_x", "no outlet for item_y", "activation below 6/min"). The title says whether the evaluation converged and in how many iterations. [Steady state](../concepts/verification/steady-state.md) explains what the evaluator models.

`--no-rates` skips the evaluator; `-o` writes the report as JSON.

## render

```bash
kohakuefda render out/layout.json
kohakuefda render out/layout.json --png out/layout.png
```

The text grid uses one character per cell: the first letter of a machine's English name over its footprint, `>` `<` `^` `v` for belt cells in their direction of travel, `=` and `|` for pipes, `S` for a belt splitter or converger, `s` for a pipe one, `+` for a belt bridge, `x` for a pipe bridge, `F` and `f` for control ports. The PNG (matplotlib, installed with the `viz` extra) draws footprints, segments and port markers.

## Editing by hand

Because `check` only needs the JSON, you can move a machine, delete a belt or change a rotation in the file and see the consequences. Useful checks to make deliberately:

- delete the belt after a machine: the machine stalls with "no outlet", and the segment before it still reports its flow;
- move a machine one cell: `geom.dangling_end` on the belt that no longer reaches its port;
- run a pipe over a machine: `geom.pipe_over_machine`;
- join two belts without a converger: `geom.merge`.

The evaluator treats a splitter or bridge that touches a machine port or another unit as directly connected, so layouts that chain units without a belt cell between them are accepted. That is an assumption about the game listed in [Assumptions](../dev/assumptions.md).
