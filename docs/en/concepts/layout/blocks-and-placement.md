---
title: Blocks and placement
summary: The engine places a machine and routes its belts in the same operation, builds the line one machine at a time from the busiest outward, then anneals it with moves that are themselves placements and routings, inside a time budget.
tags:
  - concepts
  - layout
  - placement
---

# Blocks and placement

## Blocks and groups

A **block** is a cell at an anchor with a rotation and a chosen port for every pin. Blocks come in four kinds by constraint: **free** blocks stand anywhere inside the Core AIC Area (machines, treatment units, Gas Dispersing Units, the core when its ports are used, and in Wuling the Depot Bus parts and bricks); **edge** blocks are outside inputs on a border cell of the area; **slot** blocks are Valley IV bricks on the fixed bus; the **parked** core stands anywhere out of the way when nothing is wired to it.

A **group** names free blocks the game binds: `bus` holds every Depot Bus part and every brick, `zone<n>` a Gas Dispersing Unit and the machines its zone must contain. A group has no shape of its own. What the game demands of its members is counted as **faults**: a brick whose back face (the face opposite its port) touches no bus part (DEP-06), a bus part that is not in one touching cluster with the port (DEP-09), a machine whose footprint leaves its unit's 13×13 (ENV-02), and two zones that overlap. Every fault is priced into the cost, so the search walks back to legality instead of returning an illegal layout.

## Placing is routing

There is no packing pass and no routing pass. A machine enters the layout only through one operation, which

1. rejects the position if the footprint leaves the area or lands on another machine,
2. rejects it if it takes the last port a wired pin could use — its own facing the ring, or another machine's that it now stands in front of,
3. rips every wire the footprint would cover,
4. routes each wire whose two ends are now placed, and
5. undoes all of it if any of them has no path.

So a position that cannot be wired never exists, and what a position costs is what the layout costs **with its wires in it**. A connection always costs at least one belt or pipe cell (LOG-11), so a belt is floor area exactly as a machine is, and the search cannot buy a smaller rectangle by pushing the cost into the lanes.

Nothing is allowed to congest: a lane may only enter a cell another lane holds as a legal crossing — the two running straight and perpendicular, with the ground clear under a pipe bridge — so there is no congestion to negotiate away afterwards. Every path search is also given a budget, the straight-line distance stretched by a factor plus a few cells to turn in; a path dearer than that would cost more floor than it is worth, and the search gives up instead of sweeping the grid.

## Building the line

Construction places the blocks in order and gives each the position that leaves the cheapest routed layout. The order starts with the **busiest machine** — the one with the most lanes, since every one of them is a position another machine will be chosen against — then runs producers before consumers, keeps a whole group together at its earliest member so the bus or the gas unit is down before anything must touch it, keeps the machines of one recipe together, and leaves machines nothing feeds or draws from until last.

Positions are offered in tiers, best kind first, and the first tier that yields anything decides:

1. positions that both obey the block's group rule and bring one of its ports within reach of a partner's,
2. positions that only obey the group rule — against the bus with the back face on it, or inside the zone,
3. positions that only face a partner: every anchor that puts one of this block's ports within `max_gap` cells of the port of a machine it exchanges something with, at every rotation, so the connection may run straight or turn a corner,
4. anywhere along the frontier of what is already placed.

Inside a tier the anchors are sorted by a cheap estimate — how much the rectangle grows and how far the placed partners are left — and the best `candidate_tries` of them are actually placed and routed; the cheapest routed layout wins. A machine that fits nowhere makes room: each placed partner in turn is lifted, the machine is placed in the space that frees, and the partner is put back, both or neither.

## Improving it

Improvement is simulated annealing over moves that are themselves placements and routings, and it stops on whichever comes first, the step count or the time budget. The layout left standing is the cheapest one seen, not the last one accepted.

| Move | What it does |
|---|---|
| `nudge` | One machine a single cell over: the cheap move, one placement and its routing. |
| `spin` | One machine turned where it stands, so its ports face other ways. |
| `relocate` | One machine out and back at the best anchor it can reach now. |
| `reroute` | A lane found again — one still without a path, else a routed one ripped so it can take a lane another has freed. |
| `swap` | Two machines exchange anchors, wires and all. |
| `translate` | The whole line pulled one cell toward the area's corner. |
| `compact` | A row or column nothing uses deleted, everything beyond it pulled in. |
| `insert` | A machine construction could not fit, tried again now the rest has moved. |
| `rescue` | The expensive way in for a machine still homeless: move one that is in its way, or sweep the area. |

## What it costs

The cost is the rectangle the line needs, plus:

- `w_shape` per cell of difference between its sides and `w_over` per cell beyond the square — the basement is a square, so a line of the same area that runs long and thin stops fitting long before a compact one does;
- `w_wire` per belt or pipe cell and `w_unit` per splitter or converger;
- `w_pull` per cell the line stands from the area's corner, so two layouts that differ only by a translation differ in cost;
- `w_pylon` per pylon the machines need and `w_power` per machine no pylon can reach. The machines are swept into clusters that each fit inside one pylon's 12×12 **and** still leave the pylon a free square to stand on, and the same sweep decides where the pylons finally go, so what is paid for is what gets built;
- a heavy weight per group fault, per machine still unplaced and per wire still unrouted.

## Rounds and the budget

A round is one construction and one improvement. When a round runs out of *steps* with machines still homeless, the engine tries again in an area grown by `enlarge_step` cells, with the time that is left; a round that ran out of *time* has shown nothing about the square, so it keeps what it has. The best round is the answer, ranked by machines placed, wires routed, whether it stays inside the real square, then cost. When nothing fits, the result carries `layout.too_big` with the size it needed, `layout.unplaced` per machine with nowhere to stand, `layout.unrouted` per lane with no path and `layout.uncovered` per machine no pylon reaches.

## Parameters

| Knob | Default | Meaning |
|---|---|---|
| `seed` | 0 | Random seed; with `time_budget` 0 a run is reproducible. |
| `iterations` | 3000 | Improvement moves after construction. |
| `time_budget` | 30 | Seconds the whole layout may take; 0 means the step count is the only limit. |
| `build_share` | 0.35 | Share of the budget construction may use before it stops scoring positions and takes the first that works. |
| `enlarge_rounds`, `enlarge_step` | 3, 6 | Retries in a larger area, and the cells each adds. |
| `candidate_tries`, `sweep_tries`, `victim_tries` | 12, 60, 3 | Positions placed and routed per tier, per area sweep, and machines moved aside to make room. |
| `hub_first` | 1 | Place the machine with the most lanes first. |
| `max_gap` | 3 | How far from a partner's port a position may put this block's. |
| `w_wire`, `w_unit` | 1, 2 | Weight per belt or pipe cell, and per splitter or converger. |
| `w_shape`, `w_over` | 2, 6 | Weight per cell of side difference, and per cell beyond the square. |
| `w_pull` | 0.25 | Pull toward the area's corner. |
| `w_pylon`, `w_power` | 12, 1000 | Weight per pylon, and per machine none can reach. |
| `start_temperature`, `end_temperature` | 0.02, 0.001 | Annealing temperature as a fraction of the starting cost, and of the start. |
| `move_*` | see table above | Relative weight of each move. |
| `route_iterations`, `present_cost`, `present_growth`, `turn_cost`, `bridge_cost`, `history_cost` | 30, 2, 1.5, 0.5, 4, 1 | The router's own knobs ([Routing](routing.md)). |
| `pylon` | `power_diffuser_1` | Pylon type. |
| `entry_sides` | `NW` | Border sides outside inputs may use. |
| `frame_every` | 20 | Improvement frames recorded per move. |
