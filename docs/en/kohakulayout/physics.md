---
title: Physics packs
summary: How a project states what the grid means, hook by hook, with every default that lets the framework run with no project at all.
tags:
  - kohakulayout
  - physics
---

# Physics packs

A physics pack answers one question: what does the grid mean in your game? It is a class
with an `id` and a `version`, registered by name (`gates@1`), that supplies data and
overrides hooks. `BasePhysics` gives every hook a default, so a pack conforms by
construction and overrides only what its game has.

| module | stage | what it decides | default |
|---|---|---|---|
| `fabric(params)` | data | grid size, layers, carriers with capacities, regions, entries | required |
| `library()` | data | footprints with ports (side, offset, direction, carrier) | required |
| `carriers` | 1, paths | `may_share(a, b)` on one cell, `crossing(a, b)` (forbidden, free, or a unit), `junction(carrier)`, `run_limit`, `repeater`, `transfers_through(unit_kind, carrier)` | exclusive cells, no crossings, no junctions |
| `fields` | 2, fields | `needs(cell)`, `emitters()` (kind, footprint, reach, overlap rule), `cover(world, needs)` | no fields; `GreedyCover` and `KindCover` ship as planners |
| `boundaries` | 3, boundaries | `anchors(world, cell)` for a constraint kind, `legal(world, placement)`, `outside(world, net)`, `crossing_region(carrier, region)` | every anchor in `build`; nothing extra illegal |
| `flow` | 4, flow | `split`, `merge`, `stateful`, `demand(cell, pin)`, `transfer(cell, inputs)`, `evaluates` | even split, proportional capped merge, no demands, no evaluation |
| `rules` | every | a deck of rules yielding findings after each assessment | none |
| `objective` | every | weights over metrics and extra terms | area and units |
| `diagnose` | every | the order refusals are reported in | overlap, region, port_shut, route, unrouted, field, legal |

## The shipped packs

- **null** (`templates/physics/null`): every default and a four-footprint library. It is an
  instrument, not a template: with the in-order solver it measures what a placement costs
  before any game and any strategy.
- **gates** (`templates/physics/gates`): logic gates on a grid wired like a schematic. Two
  carriers on two layers, jumpers where wires cross, free branching, an `edge` constraint for
  inputs and outputs, two rules (`gates.edge`, `gates.fanout`), an objective over area, wire
  cells and jumpers, and a tiny synth (`y = a & b | ~c`, or random circuits by seed). It is
  the instance the framework was brought up on, and deliberately unlike a factory game.
- **gates-power** (`GatesPowerPhysics`): the gates pack with a `power` field every gate needs
  and a `VDD` emitter that provides it in a square reach; the cover planner places emitters
  inside the placing transaction.

## Writing one

Subclass `BasePhysics`, set `id` and `version`, return a `Fabric` from `fabric` and a
footprint dictionary from `library`, replace the hook objects whose defaults do not describe
your game, decorate with `@register` (or advertise it as a `kohakulayout.physics` entry
point), and run the conformance levels on it: level 1 checks the data, level 2 mounts the
state checker on a world built from your pack and drives it with the in-order solver. A pack
cites the fact behind every rule and footprint in `attrs`; the framework never reads the
citation.
