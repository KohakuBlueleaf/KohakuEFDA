---
title: Solvers
summary: The solver protocol, the base solver that makes a strategy conform by construction, the shipped families and their registries, and level-3 conformance.
tags:
  - kohakulayout
  - solvers
---

# Solvers

A solver is a strategy over a context. It never sees a cell kind, a rule, a footprint's
meaning or a pack's name; it sees the netlist's structure, the anchors the builder streams,
refusals with stage names, assessments and its own state.

## The protocol and the base solver

`Solver` has an `id`, a typed `params` schema (`Param`: name, type, default, choices) and
`run(ctx, **params) -> "complete" | "incomplete" | "failed"`. `BaseSolver` gives the loop
every anytime search has: resolve the parameters, a start frame, `construct`, a frame with
the layout, `consider`, `improve`, `BudgetExhausted` caught as `incomplete`, the best
restored, an end frame. A subclass fills `construct` and `improve`. `resume` declares
whether a resumed run reaches the same layout (`exact`) or only promises to finish
(`continues`).

## The shipped solvers

| id | family | what it does |
|---|---|---|
| `inorder` | null solver | cells in flow order, each at the first anchor the world admits; the instrument every measurement is read against |
| `baseline` | coordinate | a first-complete spread on a lattice of squares with widening gaps (parallel slices through the execution slot when workers are given), then greedy shrinking: carve an empty line, press toward a side, nudge toward partners |
| `regional` | coordinate | seeded frontier construction on a clearance map, ranked by how close each cell's pins land to the pins they must reach, with restarts, regional withdrawal and refill, and the best prefix retained; then shrinking |
| `climb` | coordinate | construction by regional repair accepted on the gap delta, then hill climbing over shift, rotate, swap, cluster, reroute, cut, pull and repack moves, accepted on an area-first delta with a bounded wire tie-break |
| `anneal` | coordinate | the same trajectory with simulated-annealing acceptance and geometric cooling by charged work |
| `floorplan` | structural | a floorplan over macro instances and free leaves: the rows representation packs items with channels between rows that become reservations, mutations are screened by a surrogate (area plus a half-perimeter wire estimate) and legalised through the builder; an exact packing (CP-SAT or HiGHS, optional) can seed it |
| `skeleton` | template | the copyable minimal solver, with one improvement idea |

## Registries

Parts a solver composes from are registered, not imported by name: `solvers` (by id),
`anchors` (every, facing, frontier, group), the move names, `representations` (rows,
coordinate), `exact` (cpsat, milp when their libraries import), `screens`, `repack`
actions. A project adds its own without editing the catalog.

## Level-3 conformance

`solvers.conformance.level3(solver_id, toys)` runs a solver on toy problems with the state
checker mounted and checks what the protocol promises: it completes the toy, the best is
valid, frames start and end and the last carries a layout, the budget is charged and never
exceeded by more than one charge, a starved budget is incomplete rather than failed, the
same seed reproduces the layout and the event digest, and a run resumed from a checkpoint
reaches the same layout or a finished one, as the solver declares. Every shipped solver
passes it on the gates toy; the structural one also on the bank fixture.
