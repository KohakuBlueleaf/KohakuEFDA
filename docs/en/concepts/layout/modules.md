---
title: Modules
summary: The game's blueprint limits and how a layout is cut into modules with a build order.
tags:
  - concepts
  - layout
  - blueprint
---

# Modules

The game's blueprints hold at most a 50×50 area and 160 nodes, and share codes are server identifiers that cannot be imported from outside the game. A layout larger than that cannot be handed over in one piece, so the tool cuts it into **modules**: tiles of at most 50×50 cells, halved while a tile holds more than 160 entities, each listing the entities anchored inside it. They are numbered in build order, top-left first.

The module list is part of `layout.json`, printed by `kohakuefda layout`, and shown by the viewer, where a module can be highlighted on the grid to see exactly what to lay down next.

An entity is counted where its anchor is: a machine's top-left cell, a unit's cell, a segment's first cell. A belt that runs across a tile boundary therefore belongs to the tile it starts in; when building, lay the modules in order and continue the belts you started.
