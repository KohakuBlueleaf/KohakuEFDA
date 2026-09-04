---
title: Why KohakuEFDA
summary: What a ratio calculator leaves out, what this tool takes as input, and what it deliberately does not model.
tags:
  - concepts
  - foundations
---

# Why KohakuEFDA

## The gap

Every factory game grows a ratio calculator: enter a target, get machine counts. For the AIC that answer is necessary and not sufficient. The parts that make or break a line are physical and logistic:

- a belt moves 30 items a minute and a pipe 120, so a machine group needs a definite number of lanes, and a lane feeds a definite number of machines;
- a splitter shares round-robin over the outputs that are not backed up, so what a machine receives depends on who else is on the line;
- a liquid cannot be stored, so a line that makes a by-product fluid stops the moment the by-product has nowhere to go;
- loaders and unloaders must touch the depot bus, gas recipes must sit inside a 13×13 dispersing zone, pipes may cross belts but nothing crosses a machine, a belt run has a maximum length;
- the basement is a square of a fixed size for its level, and everything above has to fit in it.

KohakuEFDA models those rules and solves the placement and routing under them. The plan it makes is checked the way the game would check it: every belt starts at an output port and ends at an input port, every merge goes through a converger, every machine runs at the utilisation the plan expects.

## What you give it

Four things, and only four:

| Input | Form |
|---|---|
| Material supply | per raw item, units per minute or `unlimited` |
| Targets | per product, units per minute (absolute, not ratios) |
| Basement | region, which Core AIC Area, its level, its depot level |
| Mode | `area`, `machines` or `balanced`, plus flags for mixed terminal lanes and gas |

Recipe choice, machine counts, lane counts, grouping into rows, placement, routing and verification are all decided by the tool. A recipe override is the one escape hatch: it pins the recipe for one item.

## What it does not model

- **Mining.** Ore arrives at the rate you state. Mining rigs, electric rigs and belt-free delivery are outside the square and outside the model.
- **Depot capacity.** The depot is treated as unbounded. Instead of a cap, every item's net rate is reported with its sign: positive means it accumulates (fine at a terminal sink, an error on a shared path), negative means it starves, zero means balanced.
- **Time.** Everything is steady state, per minute. Startup, buffers filling, and the game's item-by-item timing are not simulated; the steady state is what the game converges to once every buffer along a path has settled.
- **The game itself.** The tool reads a normalised dataset built from published game tables and never touches a running game. Its output is a build guide: a text grid, a picture, a viewer page, and blueprint-sized modules in build order. You lay it down by hand.

## Two regions

Both regions are supported from the same code. Valley IV has no fluids, so its lines are belts only and the planner filters out every fluid recipe there. Wuling has liquids, gases, conduits, transmuters and a depot bus the player lays; its machine set is a superset of Valley IV's. The scenario's region selects the rules.
