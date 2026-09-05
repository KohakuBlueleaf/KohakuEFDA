---
title: Blocks and placement
summary: Seeded first-feasible routed spread followed by greedy compaction on the same grid.
tags:
  - concepts
  - layout
  - placement
---

# Blocks and placement

## Blocks and groups

A block is a netlist cell with an anchor, rotation and selected ports. Free blocks
stand inside the basement; edge blocks are outside-input entries; slot blocks are
fixed-bus bricks. Bus and gas-zone groups retain their attachment and containment
rules (DEP-06, DEP-09, DEP-18, ENV-02).

## Placing is routing

`Site.place` tests the footprint and port exits, rips obstructed routes, places the
machine and routes its ready connections. It also checks group rules and pylon
feasibility. Failure restores the previous state. During construction, only the
placed subset exists; a successful spread has every machine and every required
route present. The final verification stage checks geometry and production rates.

Machine-to-machine connections need a belt or pipe network cell (LOG-11), but
unconnected machine edges may touch (PLC-01). The construction lattice is an
algorithmic starting arrangement, not an additional game-clearance rule.

## The spread

The lattice pitch is the widest free block plus the selected pylon's width and
`spread_gap`. Blocks follow a depth-first flow traversal, with groups kept together
and their anchors first. Lattice positions follow a serpentine walk.

Attempts cycle through the configured gaps and both flow directions. After the
first deterministic cycle in both directions, seeded randomness changes ties in
the traversal. Each attempt places and routes machines together, retries missed
machines once, and **stops at the first complete routed spread**. Exhaustion retains
an incomplete diagnostic result with explicit findings; it does not prove that the
factory is impossible.

## The shrink

Only a complete spread is shrunk. Each round takes the first successful improvement:

| Move | Proposal |
|---|---|
| Carve | Remove a row or column containing no machine footprint. |
| Press | Press machines toward a wall without overlapping footprints. |
| Nudge | Move one machine one cell, preferring directions toward connected partners. |

Every proposal is routed and either accepted whole or rolled back. Improvement is
lexicographic: smaller occupied bounding-box area inside the basement, **including
pylons**, then fewer wire cells. Fixed slots and border entries remain pinned.
Compaction stops when no proposal improves the result or its round budget expires.

## Parallel construction

With multiple workers, independent seeded spread slices run in rounds. Each worker
stops at its first complete result. The parent waits for the round and imports the
snapshot from the lowest successful seed, so completion order does not decide the result. Shrinking
runs only once, on the selected spread. The same seed and settings reproduce the
same result; changing the worker count changes the schedule.

## Parameters

The authoritative defaults are `LAYOUT_DEFAULTS` in `layout/engine.py` and the
Studio's `/api/params` response.

| Knob | Default | Meaning |
|---|---|---|
| `spread_attempts` | 32000 | Maximum construction attempts, shared across workers; successful construction stops early. |
| `spread_slice` | 64 | Maximum attempts per worker in a parallel round. |
| `workers` | 1 | Worker count; 0 selects up to 16 available cores, 1 runs serially. |
| `seed` | 0 | Seed for flow-order retries. |
| `spread_gap`, `spread_widest` | 0, 6 | Extra corridor range beyond the pylon-width corridor. |
| `flow_order` | `bottom-up` | First flow direction; retries also try the opposite direction. |
| `shrink_rounds` | 200 | Maximum greedy compaction rounds. |
| `pylon` | `power_diffuser_1` | Pylon used for coverage. |
| `entry_sides` | `NW` | Allowed borders for outside inputs. |

Router penalties are described in [Routing](routing.md). Diagnostic `w_*` settings
belong to `Site.cost`; they do not replace the shrink pass's area/length comparison.
The board is never enlarged to conceal a layout failure.
