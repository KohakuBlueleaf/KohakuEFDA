---
title: Machines
summary: A cell is one machine; its pins are lanes on the ports the recipe binds, with every bound port as an alternative; the core, bus parts, bricks, outside inputs, zone units and treatment units are cells too.
tags:
  - concepts
  - cells
  - machines
---

# Machines

## One machine, its pins

A recipe cell is one machine at `(0, 0)` with rotation 0. For every input and output of the recipe it carries one pin per lane: an input of 60 per minute on a belt is two pins at 30, each on its own port. The pin's default port is the first bound port still free; its **alternatives** are every port the recipe binds for that item, so placement may move a lane to another port when the default faces a wall. A transmuter's activation fluid gets a pin on the one pipe port no recipe binds (6 per minute, game-knowledge ACT-03). The cell also records the environment its recipe needs (`env`) and, when a Gas Dispersing Unit serves it, the `group` of that unit.

Rotation is not part of the cell. Placement rotates the whole cell; pins turn with it.

## Cells that touch the outside

| Cell | Machine | Pins | Group | Where it may stand |
|---|---|---|---|---|
| `core` | Automation-Core 9×9 | up to 6 belt outputs (supplied solids) and 14 belt inputs (delivered and stored solids) when the scenario says `depot = "core"`; none otherwise | | inside the area; parked out of the way when unused (DEP-03) |
| `depot` | one Depot Bus Port 4×4 or one Depot Bus Section 4×8 | none | `bus` | inside the area, anywhere, any rotation (DEP-09) |
| `unloader`, `loader` | one brick 3×1 | one belt pin | `bus` | Wuling: anywhere its back face touches a bus part (DEP-06); Valley IV: on a fixed bus slot (DEP-12) |
| `entry` | none | one pipe output at the lane's rate | | one border cell of the area, the pipe leaving inward (RES-09) |
| `zone` | Gas Dispersing Unit 3×3 | one pipe input at 6 per minute | `zone<n>` | inside the area; its 13×13 zone contains its group's machines (ENV-02) |
| `dump` | Water Treatment Unit | one pipe input at 30 | | inside the area |

Solids come from and go to the depot through bricks by default; with `depot = "core"` the first six supply lanes take the core's output ports and the first fourteen delivery lanes its input ports, and only the rest become bricks. In Wuling the netlist adds one Depot Bus Port and the fewest sections whose chain seats the bricks: a chain of length `L = 4 × ports + 8 × sections` seats `2 × ⌊L / 3⌋ + 2` bricks (three cells per brick along each long side, one brick on each end), capped by the depot level's purchases (DEP-10). How the parts and bricks actually stand is the layout stage's decision. In Valley IV each brick is bound to a slot along the fixed bus.

Fluids the plan draws from the world arrive by pipe from outside the area: one `entry` cell per lane, sized so that each machine is fed whole by one lane wherever the depot's brick budget allows (game-knowledge JCT-01), and the gas of every zone unit likewise.

The plan decides how many zones an environment needs (one per 13×13 at half fill of machine footprint); the netlist assigns machines to units first-fit by footprint, a machine fitting when it is at most five cells long in the dimension that stands beside the unit, and opens another unit when the planned ones cannot hold everything.
