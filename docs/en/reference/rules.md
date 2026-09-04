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
| `layout.too_big` | error | The best layout does not fit the square; the message gives the size it needs. |
| `layout.group_faults` | error | A brick off its bus, a bus part off the cluster, or a machine outside its gas zone remains. |
| `layout.unrouted` | error | A wire found no path anywhere the machines ended up; the message names its ends. |
| `layout.unplaced` | error | No position in the square where a machine could be placed and wired; the message names it. |
| `layout.uncovered` | error | A powered machine with no free spot for a pylon within reach. |

## Geometry (verifier)

| Rule | Severity | Meaning |
|---|---|---|
| `geom.bounds` | error | Something lies outside the grid. |
| `geom.overlap` | error | Two things claim one cell on one layer. |
| `geom.pipe_over_machine` | error | A pipe cell above a machine. |
| `geom.segment_empty` | error | A segment with no cells. |
| `geom.segment_gap` | error | Two consecutive cells are not neighbours. |
| `geom.segment_loop` | error | A segment visits a cell twice. |
| `geom.run_length` | error | A belt run over 110 cells or a pipe run over 80. |
| `geom.dangling_start` | error | No output port behind a segment's first cell. |
| `geom.dangling_end` | error | No input port ahead of a segment's last cell. |
| `geom.port_shared` | error | One output port feeds two segments. |
| `geom.merge` | error | Two segments end at one input port. |
| `geom.fluid_router_count` | error | More than 128 pipe units. |
| `geom.conduit_missing` | error | A conduit link names an unknown end. |
| `geom.conduit_kind` | error | A conduit link does not join an inlet to an outlet. |
| `geom.conduit_distance` | error | Conduit ends more than 300 cells apart. |
| `geom.zone_overlap` | error | Two gas zones overlap. |
| `geom.zone_missing` | error | An environment recipe's machine is not inside one zone. |
| `geom.power` | warning | No pylon at all while powered machines exist. |
| `geom.power_uncovered` | error | A powered machine lies outside every pylon's 12×12 square. |
| `geom.core_missing` | warning | No Automation-Core in a layout with machines. |
| `geom.core_count` | error | More than one Automation-Core. |
| `geom.outside_area` | error | A production machine, zone unit, bus part or brick is not inside the Core AIC Area. |
| `geom.belt_in_ring` | error | A belt leaves the Core AIC Area. |
| `geom.depot_bus` | error / warning | A loader or unloader whose back face touches no Depot Bus part (error); no bus placed at all (warning). A Valley IV bus is located through the layout's area; without one the rule is silent for it. |
| `geom.bus_connected` | error | A laid Depot Bus section not in one touching cluster with the port, or sections without a port. |
| `geom.entry_off_border` | error | An outside input not on a border cell of the area with the outside beyond its edge. |
| `geom.entry_shared` | error | Two outside inputs on one cell. |

## Rates (verifier)

| Rule | Severity | Meaning |
|---|---|---|
| `flow.unconverged` | error | The steady state was not reached in 1000 iterations. |
| `flow.starved` | error | A recipe runs fewer machine-equivalents than the plan needs; the message names stalled machines and causes. |
| `flow.idle` | warning | A source emits nothing (no item chosen). |
