---
title: Geometry rules
summary: Every geometry rule the verifier applies, what it catches, and the game behaviour behind it.
tags:
  - concepts
  - verify
  - rules
---

# Geometry rules

The verifier reads the layout, builds the two-layer occupancy grid and the connectivity of every segment, and reports findings with an id, a severity and the entity they point at. Ids are stable and listed in [Rules](../../reference/rules.md).

## Occupancy

- **`geom.bounds`**: a machine, unit or segment cell lies outside the grid.
- **`geom.overlap`**: two things claim one cell on one layer. Machines and pipe units claim both layers; belts and belt units the ground; pipes the sky; an outside input the sky of its cell. A pipe over a belt is legal; a pipe over a machine is the special case below.
- **`geom.pipe_over_machine`**: a pipe cell above a machine footprint. Assumed illegal in the game.

## Segments

- **`geom.segment_empty`**, **`geom.segment_gap`**, **`geom.segment_loop`**: a segment with no cells, with two consecutive cells that are not neighbours, or that visits a cell twice.
- **`geom.run_length`**: a belt longer than 110 cells or a pipe longer than 80 between routers.

## Ports

A segment starts on the cell an output port faces and ends on the cell an input port faces. When several ports face the same cell, the one in line with the segment's direction wins, and a segment never ends on the port it came from. Two ports of different entities facing each other across an edge connect directly. A segment that names the outside input it starts from starts there.

- **`geom.dangling_start`**, **`geom.dangling_end`**: no output port behind the first cell, or no input port ahead of the last.
- **`geom.port_shared`**: one output port feeds two segments.
- **`geom.merge`**: two segments end at the same input port. The game has no side-loading; merges go through a converger.

## Units and conduits

- **`geom.fluid_router_count`**: more pipe units than the game allows in one basement.
- **`geom.conduit_missing`**, **`geom.conduit_kind`**, **`geom.conduit_distance`**: a conduit link names an unknown end, joins two ends that are not an inlet and an outlet, or spans more than 300 cells.

## Zones, power, area, depot, outside inputs

- **`geom.zone_overlap`**: the 13×13 zones of two Gas Dispersing Units share a cell.
- **`geom.zone_missing`**: a machine runs an environment recipe and is not entirely inside one zone.
- **`geom.power`** (warning): no pylon at all while powered machines exist. **`geom.power_uncovered`**: a powered machine whose footprint is not inside any pylon's 12×12 square; the Automation-Core powers nothing by itself (COV-01, COV-03).
- **`geom.core_missing`** (warning), **`geom.core_count`**: a generated layout has exactly one Automation-Core (DEP-03).
- **`geom.outside_area`**, **`geom.belt_in_ring`**: production stays inside the Core AIC Area and belts never leave it; pipes may cross the ring (LOG-08).
- **`geom.depot_bus`**: a Depot Loader or Unloader whose back face, the face opposite its port, touches no Depot Bus part (DEP-06); a layout with bricks and no bus at all is a warning. A Valley IV bus is located through the layout's area.
- **`geom.bus_connected`**: a laid Depot Bus Section not in one touching cluster with the port, or sections without a port (DEP-09).
- **`geom.entry_off_border`**, **`geom.entry_shared`**: an outside input off the area's border or two on one cell (RES-09).

## What the rules do not check

Rates. A layout can be geometrically perfect and still starve a machine; that is the evaluator's job, in [Steady state](steady-state.md).
