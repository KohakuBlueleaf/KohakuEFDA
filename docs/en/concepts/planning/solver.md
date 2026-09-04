---
title: Solver
summary: The mixed-integer programme behind a plan: whole machines and crafts per minute, explicit sinks and sources, activation, gas zones, the three-phase objective with player tie-breaks, and snapping to exact fractions.
tags:
  - concepts
  - planning
  - solver
---

# Solver

The planner is a mixed-integer programme solved with HiGHS. Each recipe has two variables: **crafts per minute** (continuous) and **machines** (an integer), tied by `crafts ≤ crafts_per_minute × machines`. Balances are written in crafts, so a recipe that eats two Hetonite Solution per craft contributes `−2 × crafts` to that item. The machine count is what you build; the crafts are what the machines actually do, so a line can be one whole Gearing Unit running at a twenty-fourth of its capacity when the ore is short.

## Constraints

For every item that can carry flow (recipe inputs and outputs, activation fluids, environment gases, targets, supplies), one conservation equation:

```
Σ recipes (output count − input count) × crafts
  − activation draw × machines
  − 6 × zones (for the env gas)
  + supply − target − depot − dump = 0
```

with these bounded variables:

- **supply**, one per supplied item, capped at the scenario's rate or unbounded;
- **target**, one per target: capped at the requested rate, or unbounded for `max`;
- **depot**, one per solid item, unbounded: solids may always be sent to the depot;
- **dump**, one per fluid that a placeable Water Treatment Unit accepts, unbounded: the unit destroys it at 30 per minute per machine;
- **zones**, an integer per environment: the machines that need the environment must fit in `zones` squares of 13×13 at half fill of footprint, and every zone consumes 6 per minute of its gas.

Power is not constrained: the draw of every machine is summed and reported, and the layout stage places the pylons that carry it. A transmuter draws its activation fluid per built machine. There is no variable for a fluid with no dump and no consumer, so a by-product with nowhere to go makes its producer's machines zero: the line cannot run until the by-product has a sink.

An area budget (`area_fill × square`, default half) caps the machine footprint whenever a target is `max`.

## Three phases

Targets are absolute numbers and the supply may not reach them, so the objective is solved in three passes on the same model:

1. **Scale.** A variable `z ≤ 1` with `target ≥ requested × z` for every rated target; maximise `z`. A plan with `z = 1` is `ok`; below 1 it is `degraded`.
2. **Delivery.** With `z` fixed, maximise the sum of delivered over the reference rate (the requested rate, or one machine's output for `max`). Any target that can exceed the common scale does.
3. **Cost.** With deliveries fixed, minimise machine cost. Each machine costs a weight on its count plus a weight on its footprint, chosen by the mode: `machines` (1, 0), `area` (0.05, 1), `balanced` (1, 1/9). Water Treatment Units cost the same way per unit of dump, zone units per zone. Two small tie-breaks decide between plans of equal cost the way a player would: less power drawn (`0.001` per unit) and fewer distinct recipes built (`0.05` per recipe). Supply and depot use carry a tiny cost so that the solver does not draw or discard without reason.

The tie-breaks are what keep a Reactor Crucible ahead of a Solid-Gas plus Fluid-Gas Transmuting chain when both make Liquid Xiranite with the same machine count: the crucible draws less power and needs no activation fluid.

## Exactness

HiGHS works in floating point. Every craft rate it returns is snapped to the nearest fraction with a denominator of at most 3600 (one second in a minute), machine counts are rounded to integers, and every balance in the plan is rebuilt from those with exact arithmetic. The netlist and the evaluator carry the machine count and the load (`machines_exact`, crafts over capacity) forward unchanged.

## What the solver does not decide

It does not choose ports, lanes, rows, positions or routes; those belong to later stages. It does not cap depot capacity or Protocol Capacity. It does not model time.
