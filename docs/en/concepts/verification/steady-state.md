---
title: Steady state
summary: What the evaluator models on a placed layout, how it reaches a fixed point, and how the rate rule compares the result to the plan.
tags:
  - concepts
  - verify
  - evaluator
---

# Steady state

The evaluator answers one question about a layout: once every buffer has settled, what flows on each belt and pipe, and how busy is each machine. It is a fixed-point relaxation over the connectivity graph, in exact fractions per minute.

## The model

Every segment carries an offered flow per item, capped by its capacity (30 for a belt, 120 for a pipe) and by what its target accepts.

- **Sources.** A Depot Unloader emits 30 per minute of its configured item, a Fluid Pump 60, a Gas Extractor 20; a `rate` in the entity's config overrides the number. An outside input emits its item at its rate into the pipe that starts on its cell. An Automation-Core output port emits the item its config names for that port, at the lane rate the netlist assigned.
- **Sinks.** Depot Loaders, Protocol Stashes, Automation-Cores and tanks accept everything at capacity.
- **Dumps.** A Water Treatment Unit accepts its listed fluids at 30 per minute and refuses anything else.
- **Gas zones.** A Gas Dispersing Unit accepts 6 per minute of gas.
- **Conduits.** A Conduit Inlet takes its configured item and passes it to the linked Outlet, which emits it; back-pressure at the outlet flows back to the inlet.
- **Crafters.** A machine with a recipe runs at the smallest ratio of what it has to what it needs across its inputs and of what its outlets accept to what it produces across its outputs. A machine with an activation entry stops entirely below its minimum activation flow. Outputs are shared round-robin over the connected ports the recipe binds for that item.
- **Acceptance.** A crafter takes from each incoming segment what it consumes of the items that segment has ever carried, divided over the segments carrying the same item. That is the game's back-pressure: a belt feeding a machine that consumes 10 per minute settles at 10, and a splitter upstream sends the rest onward.
- **Units.** A splitter or pipe splitter shares its inflow equally over outlets that accept anything, refilling outlets whose share was capped. A converger sums. A bridge passes each input straight through to the opposite side. A control port lets its configured item through.
- **Direct links.** Two ports facing each other across an edge behave as a zero-length segment.

## Convergence

The relaxation repeats until nothing it carries changes: flows, acceptances and conduit state. Splitter trees and feedback loops (an acid loop topping itself up) approach their fixed point geometrically rather than reaching it, so whenever every change falls below a millionth, and every 25 steps regardless, flows are rounded to the nearest fraction over 3600 and one more step must reproduce them exactly; when that rounding does not settle (a loop's fixed point need not have a small denominator), a change below a millionth counts as converged. A layout whose flows still move by more than that after 1000 steps is reported as `flow.unconverged` (a change travels one segment per step, so a long loop needs a few hundred). The rate rule allows the same millionth when it compares machine-equivalents with the plan.

## The rate rule

The evaluator's verdict on a generated layout is not "every machine at 1": a recipe the plan runs at one and a half machines has two machines whose utilisations sum to one and a half. The rule sums utilisation per recipe and requires at least the plan's exact machine count (`flow.starved` otherwise, naming the stalled machines and their causes). Sources that emit nothing are warned as `flow.idle`.

## Reading a stall

Each machine's `stalled_by` names the first cause found: `no <item>` for a missing input, `no outlet for <item>` for an output nobody accepts, `activation <item> below 6/min`, `no recipe` for a crafter without one, `no item chosen` for a source without an item. On an imported blueprint the last two usually mean the importer could not match a recipe or a pump fluid; see [Importing blueprints](../../guides/importing-blueprints.md).
