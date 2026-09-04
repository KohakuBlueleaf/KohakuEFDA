---
title: Layout
summary: Every machine is a block; placing one and routing its belts are the same operation, the line is built from the busiest machine outward and then annealed, and the result is cut into blueprint-sized modules.
tags:
  - concepts
  - layout
  - overview
---

# Layout

1. [Blocks and placement](blocks-and-placement.md): blocks and groups, why placing is routing, building the line, the moves that improve it, what a layout costs, rounds and the time budget.
2. [Routing](routing.md): wires, trunks with splitters and convergers, the pathfinder, crossings, congestion, repeaters, and how wires become segments.
3. [Modules](modules.md): the blueprint limits and the build order.

`kohakuefda layout scenario.toml -o out/` runs plan, netlist, layout and verification in one go and writes every artifact.
