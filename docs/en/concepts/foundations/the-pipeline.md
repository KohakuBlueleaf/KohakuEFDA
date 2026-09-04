---
title: The pipeline
summary: Scenario, plan, netlist, layout, evaluation, report: what each stage decides, what it writes, and which command runs it.
tags:
  - concepts
  - foundations
  - pipeline
---

# The pipeline

A run is a chain of four stages with a checkpoint after each. Each stage reads the checkpoints before it and writes its own JSON files; `kohakuefda layout` runs the whole chain at once, and the web app runs the stages one at a time, so any stage can be rerun with other parameters from the checkpoint before it.

```
scenario.toml
     |  plan            kohakuefda plan
     v
plan.json        recipes, machine counts, item balances, nets, cells, findings
     |  netlist         kohakuefda netlist
     v
netlist.json     one cell per machine with pins; the core, bus parts, bricks, outside inputs, zone units; groups; one net per item
     |  layout          seed, moves, time budget, the cost weights, the router's costs
     v
placement.json   every block's anchor, rotation and ports, the pylons, the outside inputs, the terms
layout.json      every machine, pylon, unit, belt, pipe and outside input on the area and its ring; modules
     |  verify
     v
evaluation.json  steady-state rate on every segment, utilisation of every machine
report.json      every geometry and rate finding
```

The layout stage reports frames as it goes: one per machine placed and wired while the line is built, then one whenever a move betters it. The frames are part of the record of a run and are what the web app draws live and replays.

## Plan

The planner expands the targets into the recipes that can make them, filters recipes by region and by the gas flag, resolves each target's intent (a rate, `min` as one machine of the cheapest maker, `max` as an open amount bounded by the supply and an area budget), and solves a mixed-integer programme whose variables are whole machines and crafts per recipe. Conservation holds per item: production plus supply equals consumption plus delivery plus what goes to a sink. Sinks are explicit: solids may go to the depot, dumpable fluids to a Water Treatment Unit, and nothing else may pile up. The solve maximises the common scale of the targets first, then total delivery, then minimises the cost the mode names. The result is snapped to exact fractions and every balance is rebuilt from those, so a plan never carries a rounding error. The power the machines draw is reported as a total; nothing generates it. [Planning](../planning/README.md).

The plan also carries **nets**: for every item, the flow from each producer to each consumer with the number of belts or pipes it needs, and **cells**: identical machines grouped by recipe.

## Netlist

Every recipe use becomes one **cell** per machine: the machine alone, with **pins** on the ports its recipe binds, one per lane, each carrying an item and a rate, and every bound port as an alternative. Supplied solids become Depot Unloader bricks and delivered or depot-bound solids Depot Loader bricks (the Automation-Core's ports first when the scenario asks), and in Wuling a Depot Bus Port and the sections that seat the bricks; supplied fluids become outside inputs on the area's border; dumped fluids Water Treatment Units; every environment as many Gas Dispersing Units as it needs, each heading the group of the machines its zone must contain. The netlist joins pins: one net per item, sources and sinks with the planned flow spread over them. [Cells and netlists](../cells/README.md).

## Layout

Placing a machine and routing its belts are one operation: a position is taken only if every lane it owes can be found on the same two-layer grid, and a position that cannot be wired is undone as if it never happened. The line is built a machine at a time from the busiest one outward, each taking the position that leaves the cheapest **routed** layout, and is then improved by moves that are themselves placements and routings — nudging, turning, relocating, swapping, rerouting, pulling the whole line to the corner, deleting a row nothing uses — until the time budget runs out. The cost is the rectangle, how far from square it is, every belt and pipe cell, every splitter and converger, the pylons the machines need, and every rule a group still breaks: a brick whose back face touches no bus part, a bus not one cluster around its port, a machine outside its zone. The result is cut into modules no larger than a blueprint. [Layout](../layout/README.md).

## Evaluation and report

The geometry rules check the layout the way the game would refuse it: overlaps, belts that do not reach a port, merges without a converger, runs too long, pipes over machines, machines outside a gas zone, bricks away from the bus, a bus in pieces, outside inputs off the border. The evaluator then relaxes the layout to its steady state, and the rate rule demands that every recipe runs at least the machine-equivalents the plan needs. The report holds every finding with a severity; a layout with no error passes. [Verification](../verification/README.md).

## Fixed and derived

The scenario is the only hand-written input and the only thing a user edits; stage parameters are the only other knobs. Every artifact is machine-written and machine-read; the CLI and the web app render them. Every file carries the schema version and the dataset version it was made with, so a plan is always tied to the game data it assumed.
