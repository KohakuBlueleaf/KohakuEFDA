---
title: Lanes and stability
summary: Belts and pipes per net, machines per lane, and the findings that decide whether a plan's steady state holds.
tags:
  - concepts
  - planning
  - lanes
---

# Lanes and stability

## Lane sizing

A belt carries 30 items per minute and a pipe 120 units. Every flow of an item needs `ceil(rate / capacity)` lanes. The other direction matters just as much: one lane feeds `floor(capacity / per-machine rate)` machines, and a machine whose rate exceeds one lane needs several ports, each carrying an equal share. Both numbers come from one function and are used by the netlist stage to cut rows into lane groups.

## Nets

The plan lists, per item, every producer (a recipe, or the supply) and every consumer (a recipe, the target, a sink). It splits each consumer's demand over the producers in proportion to their output, so the nets table shows one row per producer–consumer pair with its rate and lanes. Those pairs are a description of the flow, not a wiring instruction: the layout stage joins pins of the same item into one net and lets the game's round-robin splitting balance the shares.

## Findings

The stability pass reads the rebuilt balances and reports:

| Rule | Severity | Meaning |
|---|---|---|
| `flow.accumulates` | error | An item's net rate is positive with no sink: a shared belt will back up and stop its producer. |
| `flow.starves` | error | An item's net rate is negative: consumers cannot be fed. |
| `flow.depot_sink` | info | Surplus solid goes to the depot; it will fill the depot over time. |
| `flow.dump_sink` | info | Surplus fluid is destroyed by Water Treatment Units, which the plan counts as machines. |
| `flow.fluid_target` | warning | A target is a liquid or gas; it cannot be stored, so something must consume it. |
| `flow.activation` | info | A machine needs a continuous activation flow (6 per minute of Liquid Xiranite or Xiragen). |
| `flow.env_zone` | info | A Gas Dispersing Unit zone with 6 per minute of its gas is required. |
| `plan.degraded` | warning | A target was cut; the message says requested and achievable rates. |
| `plan.power` | info | The total power the machines draw; the layout's pylons carry it and nothing is generated. |
| `plan.area` | warning | Machine footprints cover more than seven tenths of the square; routing room is tight. |

A healthy plan has zero net on every item; the errors above are the only two ways a steady state can fail to exist, and the planner refuses to hand such a plan to the layout stage.
