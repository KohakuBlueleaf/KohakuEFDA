---
title: Scenarios
summary: Writing scenario.toml, supply and targets, basements, modes and flags, recipe overrides, and what a degraded plan means.
tags:
  - guides
  - scenario
  - plan
---

# Scenarios

A scenario is the only thing you write by hand. It holds the four inputs the tool takes and nothing else: supply, targets, basement, mode. Everything downstream is derived from it and the dataset.

The exact field list is in [Scenario file](../reference/scenario-file.md); this page explains how to fill it.

## Supply

```toml
[supply]
item_copper_ore = 120
item_iron_ore = "unlimited"
item_liquid_water = "unlimited"
```

Each key is an item id; the value is the rate in units per minute at which the item is available, or `"unlimited"`. Supply is what the depot (or a pump on a vein) can deliver; mining rigs, electric rigs and the depot's stock are out of scope, so the rate is your number, not a computed one.

Solid supply reaches the factory through Depot Unloaders at 30 per minute each; the layout stage places one unloader per belt of supply. Fluid supply reaches it by pipe from outside the area, one outside input per lane of up to 120 per minute, wherever the pump or vent stands. A capped supply becomes a constraint on the plan; an unlimited one only tells the plan the item is raw and need not be made.

An item that is neither supplied nor makeable by an allowed recipe stops the recipes that need it, and the plan reports it as `plan.unsupplied`.

## Targets

```toml
[targets]
item_copper_enr = 15
```

Targets are absolute units per minute of items you want delivered to the depot. There are no ratios: two targets of 10 and 20 mean those two numbers. When the supply, the region or the gas flag makes a target impossible at full rate, the plan is **degraded**: every target is scaled down by the same factor (the plan's `scale`), the achieved rate appears next to the requested one, and `plan.degraded` names each cut target. The ratio between targets is kept because that is the only fair way to cut a set of absolute numbers without asking which one matters more.

Fluid targets are accepted but flagged with `flow.fluid_target`: a liquid or gas cannot be stored in the depot, so something in the game must consume it, bottle it in a Filling Unit, or the tool's plan is a rate, not a stock.

## Basement

```toml
[basement]
region = "wuling"
basement_id = "sky_king_flats"
level = 2
depot_level = 1
```

"Basement" is this project's word for the game's **Core AIC Area**: the square in which machines can be placed. `region` is `valley4` or `wuling`; `basement_id` names the hub or outpost; `level` sets the square's size; `depot_level` sets how much depot access there is. The known basements and their squares are listed in [Dataset](../reference/dataset.md#basements). The region also filters recipes: Valley IV has no fluids and no Wuling-only machines, so a Wuling recipe is never planned there.

The depot geometry differs by region. In Wuling the Depot Bus is laid by the player from a Bus Port and Sections, and loaders and unloaders must touch it; the layout stage builds that line itself. In Valley IV the bus segments are fixed on the square's edge at positions the dataset does not yet hold, so the layout places loaders and unloaders freely and says so in the report.

## Mode and flags

```toml
mode = "area"         # area | machines | balanced
mixed_lanes = true
gas = false
```

`mode` is the tie-breaker once the targets are met: `machines` minimises the number of machines, `area` minimises their footprint, `balanced` weighs both. Belts, pipes, splitters and crossings cost nothing in any mode; only machines and area do.

`gas = false` removes gas recipes, gas machines and env-gated recipes from the search. Set it when you have not unlocked the gas industry, or when you want to see the solid-and-liquid solution first.

`mixed_lanes` allows one belt to carry several items into a terminal sink such as a Depot Loader. It never mixes items on a lane that feeds a machine.

## Recipe overrides

```toml
[recipe_overrides]
item_copper_enr = "pool_copper_enr_1"
```

When several recipes make an item, the planner chooses among all of them by cost. An override pins one recipe for one item and removes the rest from the search. Use it when the planner picks a recipe you cannot run yet, or when you want to compare two chains.

## Reading a plan

`kohakuefda plan` prints the plan's tables; [First plan](../tutorials/first-plan.md) walks them. Three questions the tables answer:

- **How many machines?** The machines table, `whole (exact)`. Build the whole number; the exact number is the utilisation the row will run at.
- **Does anything back up?** The balances table: every net must be zero. Solids with nowhere to go are sent to the depot and reported as `flow.depot_sink`; fluids with nowhere to go need a Water Treatment Unit, which the planner adds and counts as machines (`flow.dump_sink`).
- **How many belts and pipes?** The nets table. A belt carries 30 per minute, a pipe 120; every net shows the lanes it needs.

## Benchmark scenarios

The repository keeps three scenarios under `tests/fixtures/` that exercise the whole pipeline: a Valley IV battery line (solids only), a Wuling Hetonite line (crucibles, a Purification Unit, Refining and Shredding Units, Water Treatment Units, water from outside) and a gas line (Forge of the Sky inside a Gas Dispersing Unit zone, the gas piped in from outside). They are good starting points to copy.
