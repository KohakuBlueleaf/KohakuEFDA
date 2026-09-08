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

## The evaluator

`flow.evaluate(netlist, flow, fabric)` computes, for a pack's `Flow` hooks, what every
source makes and every sink receives. Every net is primed with its declared rate and the
iteration only moves downward: what the sources make merges under the carrier's capacity,
splits evenly over the net's live sinks, and each cell's `transfer` turns delivered inputs
into what its out pins may make, never above the previous round. A loop keeps its
declared rates unless a cell on it makes less. Findings: `kl.flow.starved`,
`kl.flow.capacity`, `kl.flow.loop` (info) and `kl.flow.unstable`. A pack that sets
`flow.evaluates` has these findings join every assessment.
