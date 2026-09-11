---
title: Utils and flow
summary: Builders and passes a project may call from its synth, on no framework path, and the steady-state evaluator that turns declared rates into what every pin receives.
tags:
  - kohakulayout
  - utils
  - flow
---

# Utils and flow

## Builders and passes

`kohakulayout.utils` is framework code on no framework path: the engine never calls it,
and every function can be replaced by a person writing text.

| function | what it does |
|---|---|
| `chain`, `fanout`, `bank`, `hub`, `entries`, `instantiate` | build a netlist without hand-wiring pins: pins are picked by direction and carrier from the footprint |
| `lanes(netlist, fabric)` | splits a net over its carrier's capacity into lane nets, one source pin per lane, since a pin sits on one net |
| `replicate(netlist, max_fanout, buffer_footprint)` | inserts buffer cells in a tree so no net drives more sinks than the limit |
| `surplus(netlist, sink_footprint, kind, demand)` | attaches a sink cell to every net whose rate exceeds its demand |
| `balance(netlist, demand, fabric)` | findings: unfed, starved, surplus, over capacity |
| `macros(netlist, strategy)` | groups cells into a module, a macro with a row fragment and its derived footprint, and one instance; strategies `bank`, `group`, `custom` |

## The evaluators

`flow.evaluate(netlist, flow, fabric, evaluator, layout)` runs the evaluator the name
picks from `flow.EVALUATORS`; a pack names its own in `flow.evaluator`, and one that sets
`flow.evaluates` has the findings join every assessment.

`fixedpoint` reads the netlist: what every source makes and every sink receives. Every
net is primed with its declared rate and the iteration only moves downward: what the
sources make merges under the carrier's capacity, splits evenly over the net's live
sinks, and each cell's `transfer` turns delivered inputs into what its out pins may make,
never above the previous round. A loop keeps its declared rates unless a cell on it makes
less.

`routed` reads a layout's wires. A wire is nodes and runs: a node is a pin at its attach
cell, a unit (a crossing unit, `crosses`, one node per way of travel), a cell where the
wire branches without a unit, a segment boundary, or a dangling end; a run is the path
between two nodes along a segment, in the segment's cell order when the caller says the
layout is `oriented` and else turned toward the sink pins; a pin on a unit's cell, two
pins on one cell, and the pack's `links` are runs of no cells. Each round every cell
accepts on its in runs what `accept` says and makes what `produce` says, each commodity
(`commodity`, one per source pin) shared over the runs that accept (`share`); every unit
admits what `merge_accept` allows, keeps what `passes`, and shares it; then every run
carries what was offered, scaled to what it accepts and its carrier holds. The rounds
stop when nothing moves, when the flows rounded to a denominator hold, or when the
largest move falls under `epsilon`. The evaluation carries a `RunFlow` per run (its mix,
total and capacity) and a `CellFlow` per cell (what it received and made, its load and
the pack's note).

Findings of both: `kl.flow.starved`, `kl.flow.capacity`, `kl.flow.loop` (info, the
netlist one) and `kl.flow.unstable`.
