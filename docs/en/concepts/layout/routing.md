---
title: Routing
summary: Nets become wires between pins; wires form trees and trunks with splitters and convergers; an A* with legal crossings and negotiated congestion finds the paths; repeaters, bridges and pin extension make them segments.
tags:
  - concepts
  - layout
  - routing
---

# Routing

## From nets to wires

A net names sources and sinks. The router turns it into **wires**, one per (source pin, sink pin) pair, by best-fit assignment on the current pin positions: a source pin may feed several sinks and a sink may draw from several sources, equal lanes pair with the nearest sink, and the number of wires stays small. A pipe net with several sources and several sinks becomes a **trunk**: the sources merge into one line that then splits, so the planned rates reach every sink through even splitters (game-knowledge JCT-01, JCT-02).

Wires that share a source form a **tree**: the farthest sink is routed first from the source pin's facing cell; a later one may start on any straight cell of an earlier wire of that tree, the cell in front of the port included, where a splitter is inserted with its input facing upstream, one output straight on and one to the side. Wires that share a sink join its tree the same way, through a converger whose output faces downstream. Because the game's splitters share over outputs that are not backed up, the tree delivers what each sink consumes without the router matching rates.

## The grid

Belts and belt units live on the ground layer; pipes and pipe units in the sky. Machines, pylons, bus parts and outside inputs block both. Belts are confined to the area; pipes may cross the ring (LOG-08). A pipe unit (a pipe bridge, splitter or converger) needs the ground under it free as well, and a belt may not pass under one.

The cells that pins face are **reserved** for the wires of those pins, so no other wire can wall a pin off; another wire may still cross such a cell perpendicular to the owner's straight path, which puts a bridge right in front of the port.

## The pathfinder

Each wire is an A* search on its layer from its start set to its goal set, with a turn costing a little more than a straight step and the distance to the goals' bounding box as the estimate. A cell held by another wire of the same kind may be entered only as a **crossing**: that wire must run straight through the cell, perpendicular to the move, at most one other wire may be there, and the path must leave the cell straight on. The cell becomes a bridge. Any other sharing is allowed at a price: the present penalty times the cell's history.

That price is the negotiation. After a pass over all wires, every cell held by two wires that is not a legal crossing is **overused**: its history rises, the wires through it and the wires hanging from them are ripped up, the present penalty grows, and they are routed again. A trunk's join or branch that finds no room rips the wires in its way and retries, a bounded number of times per pass. Wires learn to avoid contested cells even when momentarily free because history is charged on every entry. The loop ends when nothing is overused, stops as soon as a wire has no path and no congestion is left to negotiate, and after the last pass routes what it ripped so every wire has a path or is named. Inside the layout engine the router never gives up on a wire: a cell it cannot free names the gap or margin that grows before the next round ([Blocks and placement](blocks-and-placement.md)).

## Repeaters

A belt run may not exceed 110 cells between routers and a pipe run 80. A piece longer than the limit gets a repeater (a splitter with a single output, facing along the wire) at a straight cell before the limit.

## From wires to segments

Once every wire is routed, units are placed: a splitter at each branch, a converger at each join, a bridge at each crossing, repeaters where needed. Every wire is cut at unit cells into segments; a unit in front of a port links to the port directly. Every segment records the item it carries, its heading, and the outside input it starts from when it does, so the port or unit it comes from and goes to is never ambiguous.

The routed layout is then checked like any other: [Geometry rules](../verification/geometry-rules.md) and [Steady state](../verification/steady-state.md).
