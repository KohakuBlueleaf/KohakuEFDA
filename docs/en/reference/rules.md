---
title: Rules
summary: Every finding id the planner, netlist, layout stage and verifier can raise, with its severity and meaning.
tags:
  - reference
  - rules
---

# Rules

Ids are stable. Severity `error` fails the stage; `warning` and `info` do not.

## Plan

| Rule | Severity | Meaning |
|---|---|---|
| `plan.unsupplied` | info | An item has no allowed recipe and no supply entry; recipes that need it stay unused. |
| `plan.infeasible` | error | The solver found no feasible production. |
| `plan.degraded` | warning | A target was cut; the message gives requested and achievable rates. |
| `plan.power` | info | The total power the machines draw; pylons carry it, nothing is generated. |
| `plan.area` | warning | Machine footprints exceed seven tenths of the square. |

## Flow (plan)

| Rule | Severity | Meaning |
|---|---|---|
| `flow.accumulates` | error | An item's net rate is positive with no sink. |
| `flow.starves` | error | An item's net rate is negative. |
| `flow.depot_sink` | info | Surplus solid goes to the depot. |
| `flow.dump_sink` | info | Surplus fluid is destroyed by Water Treatment Units. |
| `flow.fluid_target` | warning | A target is a fluid and cannot be stored. |
| `flow.activation` | info | Machines need a continuous activation flow. |
| `flow.env_zone` | info | How many Gas Dispersing Unit zones an environment needs, each fed 6 per minute of its gas. |

## Netlist

| Rule | Severity | Meaning |
|---|---|---|
| `netlist.open` | error | An item flows but has no source pin or no sink pin. |
| `netlist.short` | error | Sink lanes take less than the plan needs. |
| `netlist.io_slots` | error | More depot bricks than the depot level offers seats for. |
| `netlist.bus` | info | How many Depot Bus parts seat how many bricks. |
| `netlist.zones` | info / warning | Number of gas zones; a warning when footprints need more zones than the plan counted. |
| `netlist.entries` | info | Which fluids enter at the area's border. |

## Layout stage

| Rule | Severity | Meaning |
|---|---|---|
| `layout.square_unknown` | warning | The basement's square size is unknown; 50×50 is used. |

The placement checkpoint carries the framework's assessment findings of the run's layout,
the same ids the verifier raises below.

## Geometry (verifier)

The verifier reads a layout back as a KohakuLayout problem and layout and runs the
framework's verify runner under the Endfield pack. The framework's findings:

| Rule | Severity | Meaning |
|---|---|---|
| `kl.geometry` | error | A placement off the grid or over another, a wire off its pins, a segment that is not one contiguous path, a wire whose segments do not form one tree. |
| `kl.occupancy` | error | Two occupants on one cell of one layer that the pack does not let share: two machines, a belt or pipe over a machine, two wires without a bridge between them. |
| `kl.legal` | error | A placement the pack refuses: outside the Core AIC Area, an outside input off the border or facing outward, a Valley IV brick off its slot, a Wuling brick unseated or with no bus, a bus part off the cluster, a machine outside its gas zone, a port with no cell its wire can arrive through. |
| `kl.missing` | error | A cell of the problem with no placement. |
| `kl.unrouted` | error | A net with no wire. |
| `kl.field` | error | A powered machine outside every pylon's 12×12 square. |

The pack's deck:

| Rule | Severity | Meaning |
|---|---|---|
| `endfield.area` | error | A machine not inside the Core AIC Area. |
| `endfield.belt_ring` | error | A belt leaves the Core AIC Area. |
| `endfield.run_length` | error | A belt run over 110 cells or a pipe run over 80 between units of its own net. |
| `endfield.pipe_units` | error | More than 128 pipe units. |
| `endfield.bus` | error | A laid Depot Bus part not in a touching cluster around a port; a loader or unloader off a slot whose back face seats on no bus part or fixed bus, or with no bus at all. |
| `endfield.zone` | error | A grouped machine outside its unit's gas zone, an environment recipe's machine inside no zone, two gas zones overlapping. |
| `endfield.core` | error | More than one Automation-Core. |
| `endfield.conduit` | error | A conduit link naming an unplaced end, not joining an inlet to an outlet, or with its ends more than 300 cells apart. |
| `endfield.wiring` | error | A wire that branches or merges on a cell with no junction unit, merges or splits on a port cell, ends on no port or unit, or visits a cell twice. |

## Rates (verifier)

| Rule | Severity | Meaning |
|---|---|---|
| `flow.unconverged` | error | The steady state was not reached in 1000 iterations. |
| `flow.starved` | error | A recipe runs fewer machine-equivalents than the plan needs; the message names stalled machines and causes. |
| `flow.idle` | warning | A source emits nothing (no item chosen). |
