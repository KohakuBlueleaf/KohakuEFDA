---
title: First layout
summary: Place and route the battery line, read the rule report and the rate table, render it, and open the viewer.
tags:
  - tutorials
  - layout
---

# First layout

Continues from [First plan](first-plan.md) with the same `battery.toml`.

## 1. See the cells before placing them

The layout stage places machines one by one. Every machine of the plan is a **cell** with **pins**: one pin per lane of each item on the ports its recipe binds, and every bound port as an alternative the placer may switch to. The Automation-Core is a cell too; so are the depot bricks and, in Wuling, the Depot Bus parts they must touch. [Machines](../concepts/cells/machines.md) explains the cells.

The netlist for the whole scenario:

```bash
kohakuefda netlist battery.toml
```

One table lists every cell (its kind, machine, group, size and pins) and one lists every net: the item, its planned rate, the rate the sink lanes can take, how many trunk lanes it needs, and which pins it joins. Depot Unloader bricks carry the supplied ores and a Depot Loader the batteries; in Valley IV each brick is bound to a slot along the fixed bus.

## 2. Lay it out

```bash
kohakuefda layout battery.toml -o out/
```

The pipeline plans, builds the netlist, then lays the machines into the 32×32 square of Infra-Station level 2 one at a time, belting each to the machines it feeds in the same step, seats the bricks on the bus, sets the pylons, keeps improving the result until its time budget runs out, cuts it into blueprint-sized modules and checks it. It prints:

- the text grid of the whole square: machines as the first letter of their name, belts as arrows, pipes as `=` and `|`, splitters and convergers as `S`, bridges as `+`;
- the module table (origin, size, entity count);
- the utilisation table: every machine with its recipe, its utilisation and, when it is not running, what stalls it;
- the findings table for the layout, with the error and warning counts in its title.

A clean run ends with `0 errors`. In `out/` you now have `plan.json`, `netlist.json`, `placement.json`, `layout.json`, `evaluation.json` and `report.json`.

When the line does not fit, the report carries a `layout.too_big` error with the size the line needed, and the layout is still written in that larger area so you can see it; `layout.unplaced` names any machine that found no position it could be wired in, and `layout.unrouted` any lane left without a path. The usual cause is a basement too small for the machines; a larger level, a smaller target, or a longer `--time-budget` fixes it.

## 3. Read the utilisation table

Every crafter should read 1, or the fraction the plan asked for: a recipe that needs one and a half machines shows two machines at 1 and 3/4, or one at 1 and one at 1/2, depending on how the round-robin splitters share. What matters is the sum per recipe, and the `flow.starved` rule checks exactly that: the machine-equivalents running must reach the plan's exact count. Sources (unloaders, outside inputs) read 1 when they emit; sinks read 1.

## 4. Check and render again later

The layout file is the artifact you keep. Check it on its own, write the report, and render it:

```bash
kohakuefda check out/layout.json -o report.json
kohakuefda render out/layout.json
kohakuefda render out/layout.json --png layout.png   # needs the viz extra
```

`check` runs the geometry rules and the evaluator; `render` prints the grid. Both accept a layout you edited by hand, so you can move something and see what breaks.

## 5. Open the web app

```bash
kohakuefda serve out/ --open
```

The browser page shows the loaded files. The **Layout** page draws the square with layer toggles; hovering a machine shows its recipe and utilisation, hovering a belt shows what flows on it. **Modules** lists the build order, **Plan** shows the flow graph and tables, **Report** every finding, **Dataset** the game data the run used. The language switch changes every name to the game's own Traditional or Simplified Chinese.

## What to try next

- Build the same scenario at `level = 1` (24×27) and watch the packing fail honestly.
- Plan a Wuling line with fluids: [Scenarios](../guides/scenarios.md) has one with crucibles, a purifier, Water Treatment Units and water piped in from outside.
- Import a blueprint from IndustrialPlanner and check it: [Importing blueprints](../guides/importing-blueprints.md).
