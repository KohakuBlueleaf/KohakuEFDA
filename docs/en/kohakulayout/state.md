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
| `overlap` | a cell is held by something the placement cannot displace: another cell, or a unit nobody owns; a wire or a route unit is ripped with its net and re-routed, a field emitter is placed again |
| `port_shut` | every attach cell of a pin of the new cell is held, leaves the grid, coincides with another net's open attach cell, or is boxed into a pocket too small to leave; or the new footprint covers the last open attach cell of another placed pin (a pin with a choice of ports reserves none of its attach cells while unrouted, and keeps whichever is open) |
| `field` | no emitter reaches a need and the planner cannot place one |
| `route` | a net the placement made routable (a placed source and sink) cannot be routed, a routed net cannot grow to the new pin, or a wire under the footprint cannot be re-routed |

A wire under a new footprint is ripped and re-routed when a router is installed;
`withdraw` frees the cell, unroutes its nets and drops crossing units that only existed
because of them.

## The router

The router is a slot: `route(world, net)`, `unroute`, `cost`, `forget`. The default
occupant is a negotiated-congestion path finder: a net routes at a present cost, ripping
what stands in its way, the displaced re-route in the same pass without displacing anyone, and every pass raises the
present cost until nothing stays displaced or the route rolls back; a cell a displaced wire
held is charged history through the world's undo log, so a rollback reverts the charge and
a ripped cell prices higher only where the rip stood; the search is A* on one
layer over the kernel's holder map, bounded by a detour when the costs set one, where
another net's wire is a crossing when the pack allows one and the other wire runs straight
through, shareable when the carriers say so, and otherwise a wall or a priced obstacle the
router rips. Nets
with many terminals grow as trees that keep arrivals and departures per cell: a trunk
runs from the root to the nearest sink, then the sources join with a merge wherever flow
already arrives, then the other sinks leave with a split wherever flow already leaves,
and a path never runs through a terminal it is not reaching, so every cell carries flow
one way toward a sink and no cell holds two junctions; junctions follow the pack's rule (free, a unit, or
forbidden) and a junction unit stands only on a cell free of units and crossings; another net's open attach cells are shut to a search and its routed attach cells are never ripped, a terminal cell another wire holds is ripped back or refused, never shared, and one under a footprint or another owner's unit cannot be taken; a pin with several ports is reached through whichever it may still take and the wire records the port (`Wire.ports`), so two pins of one cell never share a port; a routed attach cell counts as straight-through from its port, so a bridge may stand in front of a port; a reused crossing unit that went with a ripped net is placed again; the state checker reports two wires on one cell unless a unit carries them or the pack lets them share; reservations are corridors for their own carrier and
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
