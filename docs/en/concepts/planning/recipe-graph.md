---
title: Recipe graph
summary: How targets expand into candidate recipes, which recipes the region, the phase flags and the banned machines remove, how overrides pin a choice, which items count as natural resources, and what happens to items nobody can make.
tags:
  - concepts
  - planning
---

# Recipe graph

## Expansion

The planner starts from the targets and walks backwards. For each item it looks up every recipe whose outputs include the item; each such recipe's inputs are queued in turn. Items named in the scenario's supply are **raw** and stop the walk. The walk is breadth-first and visits each item once, so recipe cycles (a seed that grows a plant that yields two seeds) are recorded without looping. The result is the set of recipe ids the solver may use, the raw items it may draw, and the items that are neither raw nor makeable.

## Filters

A recipe is allowed only if:

- its machine is not in `banned_machines`;
- its machine may be placed in the scenario's region (Wuling-only machines carry a placement domain; Valley IV excludes them);
- in Valley IV, it uses no fluid: no liquid or gas mode, no liquid or gas item on either side;
- with `gas = false`, it has no gas mode, no environment requirement and no gas item;
- with `liquids = false`, it has no fluid mode and no fluid item.

These filters are what makes one code path serve both regions and every stage of a player's progress: the planner never knows a recipe is "a Wuling recipe" or "a late recipe", it only knows the recipe's machine, mode and items.

## Overrides

`recipe_overrides` maps an item id to one recipe id. When present, that recipe is the only candidate for the item and the filters are not consulted. Use it to force a chain you can actually build, or to compare two ways of making something by running the plan twice.

## Natural resources and gathered items

Some items no recipe makes. The dataset's `resources` table names the ones the world supplies: ores from mining rigs, water and acid from pumps, vent gases from the Gas Extractor. The Studio lists those as *what you have* with "plenty" as the default. Everything else without a recipe (Wood, for one) is **gathered by hand**: it is offered, not assumed, and the planner uses it only when the player ticks it. That is why Carbon comes from a Sandleaf plot loop, not from Wood.

## Unmakeable items

An item that no allowed recipe produces and that is not in the supply is reported as `plan.unsupplied` (an informational finding, not an error). Recipes that need it stay in the graph but cannot run, and the solver treats them accordingly. If the target itself is unmakeable the plan comes out infeasible with `plan.infeasible`.

## Several recipes per item

When more than one allowed recipe makes an item, all of them enter the solver and the objective picks the cheapest mix. Nothing prefers a "primary" recipe: two recipes that both work are a cost question, decided by machine count, power and simplicity in that order.
