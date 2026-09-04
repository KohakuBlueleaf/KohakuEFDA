---
title: Cells and netlists
summary: One cell per machine with its ports as pins; the core, the Depot Bus parts and bricks, the outside inputs and the zone units are cells too, bound into groups; and the netlist that joins their pins.
tags:
  - concepts
  - cells
  - overview
---

# Cells and netlists

Between the plan (rates) and the layout (cells on a grid) sits one abstraction: the **cell**. A cell is one machine at the origin with its ports exposed as **pins**, one pin per lane of one item. Every cell holds exactly one machine, or none for an outside input; a plan that needs eight of one machine gets eight cells that run in parallel, each placed, rotated and wired on its own.

What the game binds together is not merged into one cell but named as a **group**: the Depot Bus parts and the bricks that must touch them form the group `bus`; a Gas Dispersing Unit and the machines its 13×13 zone must contain form a group `zone<n>`. The layout stage keeps a group's cells together and counts every game rule they break, without inventing a shape for them: bricks may touch each other, any face of any part, and any other machine.

1. [Machines](machines.md): what a cell holds, how pins and their alternative ports come from the port table, and the cells that touch the outside world: the Automation-Core, the Depot Bus parts and bricks, outside inputs, Gas Dispersing Units, Water Treatment Units.
2. [Netlist](netlist.md): from balances to cells, and one net per item between pins.
