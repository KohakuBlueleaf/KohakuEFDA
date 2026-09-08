---
title: The world and the router
summary: The transactional state every solver mutates, the chain a placement must pass, the router that fills it, the kernels behind it, and the checker that makes the obligations executable.
tags:
  - kohakulayout
  - state
  - routing
---

# The world and the router

The `World` holds placements, wires, units and reservations over a per-layer occupancy
kernel. Every mutation happens inside a transaction and is journaled, so a refused `place`
or `route` leaves the digest unchanged and a solver can mark and roll back inside one.

## The placement chain

`place(cell, x, y, rot)` runs the failure chain, then occupies, asks the pack's `legal`,
covers the cell's field needs through the cover planner, and routes every net the placement
completes. The chain names its stage:

| stage | refused when |
|---|---|
| `legal` | the rotation is not one the footprint allows, or the pack's `legal` hook says no |
| `region` | a cell leaves the grid or the build region |
| `overlap` | a cell is held by something the carriers say cannot share it |
| `port_shut` | an attach cell of the new cell is held, leaves the grid, coincides with another net's open attach cell, or is boxed into a pocket too small to leave; or the new footprint covers another placed cell's open attach cell |
| `field` | no emitter reaches a need and the planner cannot place one |
| `route` | a net the placement completed cannot be routed, or a wire under the footprint cannot be re-routed |

A wire under a new footprint is ripped and re-routed when a router is installed;
`withdraw` frees the cell, unroutes its nets and drops crossing units that only existed
because of them.

## The router

The router is a slot: `route(world, net)`, `unroute`, `cost`, `forget`. The default
occupant is a negotiated-congestion path finder with rip-up: A* on one layer over the
kernel's holder map, where another net's wire is a crossing when the pack allows one and
the other wire runs straight through, shareable when the carriers say so, and otherwise a
wall or, with rip-up on, a priced obstacle the router rips and re-routes afterwards. Nets
with many terminals grow as trees: the sources join first into a trunk, then the sinks
branch from the last join or from one another, so every cell carries flow one way;
junctions follow the pack's rule (free, a unit, or forbidden) and a join prefers a cell
where the junction unit can stand; reservations are corridors for their own carrier and
walls for any other; a unit a route needs may take a field emitter's cell, and the
emitter is placed again for every cell it left short; run limits place repeaters, and without a repeater only a run over
the limit is refused. Everything the router writes goes through `set_wire`
and `place_unit`, so it rolls back with the attempt.

## Kernels

The kernel is the occupancy grid behind the world: `occupy`, `free`, holders per cell,
`free_for`, `cells_of`, `extent`, `occupancy`, `integral`, `save` and `load`. Two occupants
agree byte for byte: the pure Python `PyKernel` and the native `Grid` from the Rust twin
(`make_kernel("auto")` picks the twin when built). A `RecordingKernel` logs every mutation
as JSON lines and `replay` drives any kernel with the log, which is how the twin's parity
is measured on real runs.

## The state checker

`StateCheck` mounts on a world and raises on the first broken obligation: a refused place
or route that moved the digest, a refusal without a stage, holders that disagree with the
record, a reservation crossed by another carrier, a restore that reallocated the kernel.
Every conformance run mounts it.
