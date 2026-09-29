---
title: Layout solvers
summary: The project's guided search on KohakuLayout, the framework solvers the studio also offers, the stage knobs around them and the bench that measures them.
tags: [dev, algorithms, layout]
---

# Layout solvers

The layout stage runs one KohakuLayout solver on the synth's problem. The studio and the
CLI offer every solver the project and the framework ship, under its id without the
`endfield.` prefix: `guided` (the default), `baseline`, `regional`, `climb`, `anneal`,
`floorplan` and `inorder`. Each declares its parameters; the studio shows them typed, a
choice parameter as a list.

## guided

`endfield.guided` seeds a complete layout, then improves it by local search over free
coordinates.

| Phase | What happens |
|---|---|
| Seed, `seed_kind="lines"` | The community's line shape (PLC-09 to PLC-13): rows by depth from the Depot Bus, the unloaders in front of the machines they feed, side cells beside their machine, groups packed against the bus faces. The whole structure is placed as one batch with its lanes reserved, then routed; it must land complete within `seed_units` actions. |
| Seed, `seed_kind="regional"` or a lines seed that did not land | Regional construction by repair steps: unwired cells first, then cells with a placed lane neighbour, anchors pulled toward a force-directed embedding of the lane graph. |
| Improve | The framework's local moves (shift, rotate, swap, cluster, reroute, cut, pull, press) accepted by `acceptance` (`climb` or `anneal`) on an area-first delta; every `repack_every` proposals a neighbourhood is withdrawn and refilled; every `reseat_every` proposals a Depot Loader or Unloader moves to another legal slot, alone or with one partner. |

Anchors are ranked by contact scoring: every pin of the cell is assigned a distinct port
against the cells the lane router would open on its partner's lanes (`assignment.py`),
plus extent growth, a pull toward the area's corner and alignment with same-sized
footprints. Repair grows its region around the endpoints the last `conflict_window`
refusals name. `batch_moves` settles every footprint of a relocation before routing any,
so a valid final arrangement is not refused for an impossible intermediate one.
`adaptive_moves` draws the ordinary operators by their recent reward per square root of
charged work, with `operator_exploration` of the draws uniform. Every proposal stays one
journaled attempt: a refused route or an exhausted budget restores the world.

The defaults are the measured study profile: lines seed, `reseat_every` 12, adaptive
moves, batch moves.

## The framework solvers

`baseline` spreads and shrinks, `regional` constructs by frontier insertion and shrinks,
`climb` and `anneal` run the generic local search, `floorplan` legalises a rows
floorplan, `inorder` places every cell at its first admitted anchor. They carry no
project rule; `floorplan` legalises its whole structure at once and lands nothing on the
bundled scenarios. See [KohakuLayout solvers](../kohakulayout/solvers.md).

## Stage knobs

| Stage | Parameter | Values |
|---|---|---|
| netlist | `transport` | `legacy` machines at nominal rates; `rated` exact operating points with full lanes before a partial one; `direct` the rated netlist re-laned by the transport allocator (`plan/transport/`), the rated one kept with a warning when no allocation exists |
| verify | `initial` | `empty` runs, or `declared`: every net primed with its declared flow (a primed steady state, not a cold start) |

## The bench

`scripts/dev/bench/run.py run` lays out a grid of cases, transports, solvers and seeds, each
trial in its own process, and keeps everything on disk: the first routed, best and
diagnostic layouts with their terms, geometry findings, complexity and the routed
evaluation from both initial states, then a ledger, the winners and `report.html`. A trial
is verified when every cell is placed, the best layout has no geometry error, and the
declared evaluation converges without a rate error.
