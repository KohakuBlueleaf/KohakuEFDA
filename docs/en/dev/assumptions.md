---
title: Assumptions
summary: Game mechanics the tool assumes without in-play verification, gaps in the dataset, and known limits of the current stages.
tags:
  - dev
  - assumptions
  - limits
---

# Assumptions

Everything on this page is either an assumption about the game that the tool relies on, a hole in the data, or a limit of the current algorithms. Each says where it is used. Game facts themselves live in the project's game-knowledge notes and are cited by id.

## Assumed game mechanics

- **Pipes over machines are illegal.** `geom.pipe_over_machine` is an error; the router never routes a pipe across a footprint.
- **Adjacent facing ports connect directly.** A splitter, converger or bridge touching a machine's port, two units side by side: all treated as connected with no belt cell between them. The router relies on it where a branch, join or crossing lands in front of a port. `layout/connect.py`, `route/router.py`.
- **A Depot Bus chain seats one brick per three cells of long side and one per end**, and nothing constrains how parts and bricks stand beyond touching: a brick's back face on any part, bricks side by side, any two units side by side (DEP-06, DEP-09, DEP-17). Used to count sections and to judge a placement. `layout/depot_via.py`, `layout/groups.py`, `verify/rules/geometry.py`.
- **A Gas Dispersing Unit consumes 6 per minute of its gas** and its zone is 13×13 centred on it; an environment needs one unit per 13×13 at half fill of machine footprint, and a machine fits a zone when it is at most five cells long in the dimension beside the unit (ENV-01, ENV-02). `model/sinks.py`, `plan/lp.py`, `plan/zones.py`, `layout/coverage.py`.
- **A transmuter draws its activation fluid per built machine**, idle or not (6 per minute from the tables); `activation = "duty"` charges per machine-equivalent instead (ACT-03). `plan/lp.py`, `plan/planner.py`.
- **A machine is powered when its whole footprint lies inside a pylon's 12×12 square**; the Automation-Core powers nothing by itself (COV-01, COV-03). Power is reported as the total the machines draw; no generation is planned or placed (PWR-05). `layout/coverage.py`, `verify/rules/geometry.py`, `plan/planner.py`.
- **Fluids enter by pipe from outside the area** (RES-09): every supplied liquid or gas is an outside input on the border, at up to 120 per minute per pipe, wherever the world's pump or vent stands. `plan/machines.py`, `layout/engine.py`. Pumps, extractors and vents are not placed.
- **Natural resources.** Ores (Originium, Amethyst, Ferrium, Cuprium) come from mining rigs and arrive through the depot; Clean Water, Precipitation Acid and the four environment gases come from outside. `data/static/resources.json`.
- **A Planting Unit turns a seed into a plant every 2 s and a Seed-Picking Unit a plant into two seeds every 2 s**, as the tables say; plots and growth time are not modelled (PLT-04). `plan/recipes.py`.
- **A Protocol Stash needs to be inside pylon range** (it draws power). Warning only.
- **Splitters share evenly over outputs that are not backed up** (JCT-01), and a crafter accepts from a belt exactly what it consumes. The evaluator's whole model of back-pressure rests on this; the netlist packs supply lanes so that one lane feeds each machine whole, and the router merges many-to-many pipe nets into a trunk before splitting.

## Data gaps

- **Traditional Chinese names** are missing for some entries (Wuling outposts, the Sewage Inlet); the glossary shows blanks and names fall back to Simplified Chinese or English.
- **Pictures** are missing for 66 entries of the wiki; the Studio shows a neutral glyph for them.
- **IndustrialPlanner's `chrono` recipe variants** have no verified counterpart in the tables.

## Known limits

- **Local compaction.** The first complete routed spread is greedily shrunk; this does not prove minimum area or infeasibility when construction exhausts its budget.
- **Construction cost.** Routing and coverage checks run during placement. The optional Rust grid accelerates routing, while snapshots and whole-layout compaction proposals still cost time.
- **Recycle loops.** The evaluator starts with empty flows and can settle a seed/plant recycle loop at zero. A complete geometric layout is not a certificate that rate verification will pass.
- **Depot via.** A solid could travel through the depot (loader in, unloader out) instead of a belt; the netlist marks such nets but the router always lays a belt.
- **Reactor Crucible channels.** A crucible running two chained recipes in IndustrialPlanner is imported with one.
- **Time.** Only the steady state is modelled; buffers, startup and the game's item-level timing are not.
- **Protocol Capacity** is recorded per machine but not constrained.
