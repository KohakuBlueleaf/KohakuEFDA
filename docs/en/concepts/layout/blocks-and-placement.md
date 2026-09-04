---
title: Blocks and placement
summary: Placing a machine and routing its belts are one operation, so a layout is whole or it is nothing; machines are spread over a derived lattice, the room is squeezed back out, and three searches run over the few decisions the spread actually makes.
tags:
  - concepts
  - layout
  - placement
---

# Blocks and placement

## Blocks and groups

A **block** is a cell at an anchor with a rotation and a chosen port for every pin. Blocks come in four kinds by constraint: **free** blocks stand anywhere inside the Core AIC Area (machines, treatment units, Gas Dispersing Units, the core when its ports are used, and in Wuling the Depot Bus parts and bricks); **edge** blocks are outside inputs on a border cell of the area; **slot** blocks are Valley IV bricks on the fixed bus; the **parked** core stands anywhere out of the way when nothing is wired to it.

A **group** names free blocks the game binds: `bus` holds every Depot Bus part and every brick, `zone<n>` a Gas Dispersing Unit and the machines its zone must contain. A group has no shape of its own. What the game demands of its members is counted as **faults**: a brick whose back face (the face opposite its port) touches no bus part (DEP-06), a bus part that is not in one touching cluster with the port (DEP-09), a machine whose footprint leaves its unit's 13×13 (ENV-02), and two zones that overlap. A placement that leaves a fault is refused outright.

## Placing is routing

There is no packing pass and no routing pass. A machine enters the layout only through one operation, which

1. rejects the position if the footprint leaves the area or lands on another machine,
2. rejects it if it takes the last port a wired pin could use — its own facing the ring, or another machine's that it now stands in front of,
3. rips every wire the footprint would cover,
4. routes each wire whose two ends are now placed,
5. rejects it if a group rule is broken or a machine is left where no pylon can reach it, and
6. undoes all of it if any of that fails.

So a position that cannot be wired never exists, and a layout is **whole or it is nothing**: every machine standing, every lane routed. A connection always costs at least one belt or pipe cell (LOG-11), so a belt is floor area exactly as a machine is.

Nothing is allowed to congest: a lane may only enter a cell another lane holds as a legal crossing — the two running straight and perpendicular, with the ground clear under a pipe bridge — so there is no congestion to negotiate away afterwards. Every path search is given a budget, the straight-line distance stretched by a factor plus a few cells to turn in; a path dearer than that would cost more floor than it is worth.

## The spread

Machines go into the squares of a lattice. The step is **derived, not tuned**: the widest free block plus the one cell a connection always costs. A pylon needs no room beside its machine, because partial coverage powers a machine and a single shared cell is enough (COV-02), so a pylon reaches from any corridor whose square overlaps it.

Clearance is derived per edge too: one free cell where a wired port sits on that edge, and none where no port does, because machines may share edges (PLC-01). A machine whose ports are all on two opposite faces therefore packs solid against its neighbours on the other two.

Blocks are laid in the order the flow visits them, **each chain walked to its end** before the next starts, so a machine lands beside the one that feeds it; and the squares are taken in a serpentine, so the walk turns back on itself at the end of a row rather than jumping home. Taking the flow one rank at a time instead — every machine of a step side by side — left each consumer wherever the walk had got to, and the lanes then cost more floor than the machines: 611 lane cells against 82.

Nothing is ever moved aside to make room. A lattice either comes out whole or it is thrown away and laid again from a different order, which costs a few hundredths of a second.

## The shrink

The spread is legal but loose. Shrinking takes the room back out and only ever *removes* space, so it cannot strand a machine or a lane — the worst a round does is find no improvement and stop. Three moves, tried in that order:

| Move | What it does |
|---|---|
| `carve` | A row or column no machine stands on deleted, everything past it slid in; the lanes crossing it come back a cell shorter. |
| `press` | Every machine slid as far as it goes toward one wall, nearest the wall first. |
| `nudge` | One machine moved a cell toward what it is wired to. A press moves everything at once and a dense layout often will not route, so it is rejected whole; one machine only disturbs its own lanes. |

Each proposal is a complete layout, rebuilt and rewired, and it is kept only when it still stands whole and is smaller — area first, lane cells second.

## The search

Once three choices are fixed the spread is deterministic: the order the blocks are laid in, the corridor width, and which way along the flow the walk runs. Those are the **genome**, the spread is its **decoder**, and everything else about a layout follows from them.

The order the spread starts from is worth keeping, so mutation disturbs it locally — neighbours exchanged, a run reversed, one block carried elsewhere — and order crossover keeps a run of one parent where it is and fills the rest in the other parent's sequence, so a chain of the flow that worked survives whole into the child.

| Search | What it does |
|---|---|
| `restart` | Independent draws; keeps the best and never looks at what the last was worth. |
| `anneal` | Walks to a neighbouring genome, accepting a worse one less and less often. |
| `evolve` | Keeps a population, breeds the survivors, replaces the worst. |
| `mixed` | All three, dealt out across the cores. The default. |

None of them wins on every factory — annealing takes the small scenarios, evolution the large — and the cores to run all three are already there, so the default deals them out and keeps the best. Against independent draws that is about a sixth of the area off the largest bundled scenario and a quarter to a half of the lane cells everywhere.

Searches are independent, so they run one per core from different seeds in rounds: every worker takes the same slice of the budget, the round is waited out in full, and the best whole layout wins with ties going to the lowest seed. Taking whichever finished first would make the result depend on how loaded the machine was, and a run with a seed has to give the same layout every time.

## What it costs

A layout is scored on the **area of the rectangle it needs, then its lane cells**. Nothing else: the machine count is fixed by the plan, and power is reported rather than planned. Weights (`w_wire`, `w_shape`, `w_pull`, …) remain for the cost function the checks and the viewer report, but the search itself sorts on whole-first, then area, then lanes.

When nothing fits, the result carries `layout.too_big` with the size it needed, `layout.unplaced` per machine with nowhere to stand, `layout.unrouted` per lane with no path and `layout.uncovered` per machine no pylon reaches. The area is what the basement gives and is never enlarged to make a layout fit.

## Parameters

| Knob | Default | Meaning |
|---|---|---|
| `search` | `mixed` | Which search runs: `mixed`, `anneal`, `evolve` or `restart`. |
| `spread_attempts` | 32000 | Complete layouts tried before the search settles, shared over the workers. |
| `seed` | 0 | Fixes the randomness; the same seed and settings give the same layout. |
| `workers` | 0 | Searches at once; 0 asks the machine what it can spare. |
| `spread_slice` | 64 | Steps each core takes before the results are compared. |
| `spread_gap`, `spread_widest` | 0, 6 | Extra corridor beyond the derived clearance, and the widest the search will try. |
| `flow_order` | `bottom-up` | Which end of the production chain the machines are laid from. |
| `candidate_tries` | 12 | Positions tried for one block before moving on. |
| `shrink_rounds` | 200 | How many times the finished layout is squeezed. |
| `w_wire`, `w_unit` | 1, 2 | Weight per belt or pipe cell, and per splitter or converger. |
| `w_shape`, `w_over` | 2, 6 | Weight per cell of side difference, and per cell beyond the square. |
| `w_pull`, `w_pylon` | 0.25, 12 | Pull toward the area's corner, and weight per pylon. |
| `route_iterations`, `present_cost`, `present_growth`, `turn_cost`, `bridge_cost`, `history_cost` | 30, 2, 1.5, 0.5, 4, 1 | The router's own knobs ([Routing](routing.md)). |
| `pylon` | `power_diffuser_1` | Pylon type. |
| `entry_sides` | `NW` | Border sides outside inputs may use. |
| `frame_every` | 20 | How often a picture of the layout in progress is recorded. |
