---
title: Planning
summary: How the planner decides which recipes run, on how many machines, through how many lanes, and whether the result is stable.
tags:
  - concepts
  - planning
  - overview
---

# Planning

The planner answers the logical question before any geometry: given supply, targets, a region and a mode, what runs and at what rate. It works in exact fractions per minute and produces the plan every later stage builds on.

1. [Recipe graph](recipe-graph.md): expanding targets into candidate recipes, the region and gas filters, overrides, and items that cannot be made.
2. [Solver](solver.md): the linear programme, its sinks and sources, activation and gas zones, the three-phase objective, and snapping to exact fractions.
3. [Lanes and stability](lanes-and-stability.md): belts and pipes per net, machines per lane, and the findings that say whether the steady state holds.

Commands: `kohakuefda plan scenario.toml` prints the plan; `-o plan.json` writes it. [First plan](../../tutorials/first-plan.md) reads the tables one by one.
