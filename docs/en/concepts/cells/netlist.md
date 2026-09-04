---
title: Netlist
summary: How a plan becomes one cell per machine plus the core, bus parts, bricks, outside inputs, zone units and treatment units, and how their pins are joined into one net per item.
tags:
  - concepts
  - cells
  - netlist
---

# Netlist

The netlist is the plan made physical enough to place: a list of cells with pins and groups, and a list of nets joining pins.

## From uses to cells

Every recipe use in the plan becomes as many recipe cells as it has whole machines. The plan's balances add the cells that touch the outside world:

| Balance | Cells |
|---|---|
| a supplied solid | one Depot Unloader brick per belt lane (after the core's output ports when the scenario asks for them) |
| a supplied liquid or gas | one outside input per pipe lane, on the area's border |
| a delivered or depot-bound solid | one Depot Loader brick per belt lane (after the core's input ports when asked) |
| a dumped fluid | one Water Treatment Unit per 30 per minute |
| an environment | one Gas Dispersing Unit per zone, each heading the group of the machines it serves, with its gas as an outside input |
| bricks in Wuling | one Depot Bus Port and the fewest sections whose chain seats them, all in the `bus` group |

Supply lanes are packed by their sinks (first-fit decreasing) so that one lane feeds each machine whole and even splitters deliver the planned rates; when that needs more bricks than the depot level offers, the lanes fall back to the fewest the rate allows.

## From pins to nets

Pins of the same item are collected: every output pin is a source, every input pin a sink. One net per item records both sides, the plan's steady-state flow of the item (`rate`), the sum of what the sink lanes can take (`nominal`), the number of trunk lanes the flow needs, and whether the item may travel through the depot instead of a belt (a solid flowing between two machines). Each pin is given a planned rate in proportion to its lane rate, so the sum over sources and the sum over sinks both equal the net's rate.

A net does not say which source feeds which sink; the router decides that, and the game's round-robin splitting balances what the router connects.

## Findings

| Rule | Severity | Meaning |
|---|---|---|
| `netlist.open` | error | An item flows in the plan but has no source pin or no sink pin. |
| `netlist.short` | error | The sink lanes of an item take less than the plan needs. |
| `netlist.io_slots` | error | More depot bricks than the depot level offers seats for. |
| `netlist.bus` | info | How many Depot Bus parts seat how many bricks. |
| `netlist.zones` | info / warning | How many gas zones the netlist carries; a warning when the machines' footprints need more than the plan counted. |
| `netlist.entries` | info | Which fluids enter at the area's border. |

`kohakuefda netlist scenario.toml` prints the cells and nets; `-o netlist.json` writes them.
