---
title: Studio
summary: Design a production line in the browser: say where you are, what you want and what you have, build it stage by stage, watch the layout search and the detailed pass, grow the line from its outcomes.
tags:
  - guides
  - studio
  - web
---

# Studio

The Studio is the web app built into the Python package plus a JSON API on the same local server. It is meant for players: everything is chosen from lists with pictures and names, and the tool works out the recipes, the machine counts, the belts and pipes, and how many depot bricks and outside inputs bring the materials in.

```bash
kohakuefda data icons          # once: pictures for items and machines
kohakuefda serve out/ --open
```

The server listens on `127.0.0.1:8765` (`--port` changes the port, `0` picks a free one; `--host 0.0.0.0` opens it to the network). Every line built in the browser is kept under `out/runs/<id>/`. `--workers` sets how many stages may run at once; `--no-api` serves an artifact folder only. `kohakuefda view` is the same command.

The header switches the language (EN / 繁中 / 简中) and the light or dark theme; the status bar shows the game data version, the open run and what it is doing.

## Design

The left panel is the design entry, in four steps.

1. **Where are you.** Region, Core AIC Area, level (the level sets the square you can build in) and depot level.
2. **What do you want.** *Add a product* opens a picker with pictures; the list holds only items the region can make. Each product gets an intent: *Just make it* (the smallest line that works: one machine of the last step, fed properly), *As much as fits* (the biggest line the square and the materials allow), or *Exactly* a rate per minute.
3. **What you have.** The tool lists the natural resources the products need, each with a picture and where it comes from (mined ores, pumped water and acid, vent gases). Leave the field empty when you have plenty; otherwise type how many arrive per minute. The tool sizes the bricks and the outside inputs. Items nothing in the factory makes (Wood, say) are listed apart as *gathered by hand only* and are used only when ticked, so the planner grows Carbon from a plot loop rather than assuming an endless wood pile. *I already have some intermediate items* turns an intermediate into a supply. Removing a material tells the tool you do not have it.
4. **How to build it.** *Simplest line* (fewest machines, some may idle) or *Most efficient* (smallest area for the output). Say whether you can use liquid machines and gas machines, and ban any machine you cannot build yet; the picker shows pictures. *Advanced* holds the balanced mode, mixed belts into the depot, the area budget for *as much as fits*, and forced recipes.

The examples menu loads a bundled line; the arrows import and download `scenario.toml`; the reset button starts over.

**Build** creates a run and immediately plans it and builds its cells, so the outcomes appear at once. **All the way** also lays out and checks.

## The flow

Four stages with checkpoints run across the top: Plan, Cells, Layout, Check. A stage card shows its status and duration and has run, run-to-the-end and stop buttons; a stage can run once every earlier stage is done, and running a stage clears every later one. The settings panel on the right holds the selected stage's parameters for spread construction (attempt budget, workers, seed, gaps and flow direction), greedy shrink, spatial diagnostics and routing penalties, its error text and its history. What you type stays typed until you press reset, and every number may take any value from its minimum up. Changing a parameter and rerunning from the middle is the normal way to work: rerun Layout with another seed or a wider gap on the same cells.

Clicking a stage card shows its view:

**Plan.** The result, machine count, the power the machines draw (pylons carry it; nothing is generated), and machine cells, then the **outcomes board**: what is *made* (delivered to the depot as products), *stored* (surplus solids sent to the depot), *treated* (fluids such as sewage treated and returned outside), *used* (materials drawn from the depot or from outside), and any product that was *not possible*. Hovering a card shows **Use it**, which lists what the item could be turned into, with pictures, the machine and the rate the current flow would give; pick one, choose *matching rate* / *just make it* / *as much as fits*, then **Add to the line** (keeps the current products) or **Replace the product**. The line grows a stage and is planned again; the earlier run stays in the run list. Below: the flow graph, one node per recipe named by what it makes and the machine that makes it, sources named *from the depot* or *from outside*, edges drawn as right-angled lines on their own tracks so none runs under a node, every crossing marked with a hop and counted above the graph, feedback edges returning as dashed lines under the graph, self-feeding loops as return arrows; then the tables.

**Cells.** One card per machine with a small picture, the machine, its group (the bus, a gas zone) and its pins.

**Layout.** The line as it is built, one machine at a time with the belts and pipes it needs already on the grid, then as the moves improve it, with the cost curve beside it: bricks on the bus, outside inputs on the border, every belt and pipe coloured by what flows on it (pipes dashed); then the result with its pylons and their squares. The timeline scrubs through every recorded frame (play, step, speed, follow), and *Show the result* jumps to the end.

**Check.** The finished layout with badges for what takes from the depot (⇩), sends to the depot (⇧), comes from outside (≈) and returns outside (⇣); hover a machine for how busy it is and what it waits on, a belt or pipe for what flows on it, an outside input for what enters and from which border. Chips count errors, warnings and notes; links open the layout, blueprint tiles and report pages.

## Runs

The runs page lists every line built, newest first, with its products, area, mode and the four stage dots. Open one to continue where it stopped; delete removes its files. Runs survive a server restart.

## Result pages

**Plan**, **Layout**, **Blueprint tiles** and **Report** show the open run in full: the plan tables with pictures, the layout with all toggles, the tiles in build order (click one to highlight it on the layout), and every finding. **Game data** browses items, machines and recipes with pictures and a filter.

## Serving a folder without the API

Any folder with the tool's JSON files works, including one holding only `plan.json` from `kohakuefda plan -o`. The dataset version is read from the artifacts; `--version` overrides it, and when nothing names a version the newest dataset under the data root is used.
