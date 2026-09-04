---
title: The factory model
summary: The grid, its two layers, machine ports, belts and pipes, splitters and convergers, sources and sinks, the depot, basements, gas zones and power, as the tool models them.
tags:
  - concepts
  - foundations
  - game-model
---

# The factory model

Everything the tool decides rests on a small set of facts about the AIC. They come from the game's own tables (footprints, ports, rates, limits) and from play (how splitters share, what may cross what). This page states them as the tool uses them; the ones that are assumptions rather than table facts are marked and collected in [Assumptions](../../dev/assumptions.md).

## The grid and its layers

A basement is a square of cells. Coordinates run x to the right and y down; a machine's anchor is its top-left cell and rotation is clockwise in quarter turns. Two layers exist: the **ground**, where machines, belts, belt splitters, convergers, bridges and control ports sit; and the **sky**, where pipes run at height. Pipe splitters, convergers, bridges and control ports stand on the ground and reach the sky, so they occupy both layers. Consequences the rules enforce: a pipe may pass over a belt in any direction without a bridge; a belt may not pass under a pipe unit; nothing crosses a machine, and a pipe over a machine is treated as illegal (assumption).

## Machines and ports

A machine has a footprint (width × depth), a height, a power draw, a Protocol Capacity cost (recorded, not yet constrained), and **ports**. A port sits on one cell of the footprint, faces one edge, carries belts or pipes, and is an input or an output. Rotating the machine rotates its ports. The pattern is the same for every production machine at rotation 0: belt inputs on the north edge, belt outputs on the south, pipe inputs on the west, pipe outputs on the east; the two Transmuting Units add a pipe input on the north for their activation fluid.

A recipe binds each of its items to specific ports through **buffers**: a product may leave through several ports, and a machine with several ports for one product emits round-robin over the ports that are connected. A crafter needs every input and an accepted outlet for every output; it runs at the smallest ratio among them.

## Belts and pipes

A belt carries 30 items per minute, a pipe 120 units. A run of belt may be at most 110 cells long between routers, a run of pipe 80. Belts and pipes are directional: a segment starts on the cell an output port faces and ends on the cell an input port faces, and it turns freely on the way. A belt carrying several items (a **mixed lane**) is allowed only into a terminal sink.

**Conduits** carry a fluid underground between a Conduit Inlet and a Conduit Outlet up to 300 cells apart; the inlet takes one configured item.

## Splitters, convergers, bridges, control ports

- A **splitter** has one input and up to three outputs and shares round-robin over the outputs that are not backed up. The tool relies on that for everything: a lane tapped by splitters delivers to each machine what it consumes, without rate matching.
- A **converger** merges up to three inputs into one output. There is no side-loading: two belts into one port is an error; the merge goes through a converger.
- A **bridge** lets two belts (or two pipes) cross at one cell, each straight through.
- A **control port** lets one item through. The layout never places one; the evaluator understands one when it meets it.
- Two logistics units, or a unit and a machine port, that face each other across a shared edge connect directly, with no belt cell between them (assumption).

## Sources and sinks

- **Depot Unloader**: one belt output at 30 per minute of a chosen item. Its back must touch the Depot Bus.
- **Depot Loader**: one belt input at 30 per minute, any item, into the depot. Also on the bus.
- **Fluid Pump** (60 per minute) and **Gas Extractor** (20 per minute) supply fluids from a vein; the tool takes the fluid as given and brings it into the area by pipe from outside (RES-09), so neither is placed.
- **Protocol Stash**, **Automation-Core** and **Sub-PAC**, **Fluid Tank** and **Gas Tank**: accept at capacity. The tool treats them as sinks when it meets them in a layout but does not place them.
- **Water Treatment Unit**: destroys sewage and xiranite by-product liquids at 30 per minute. The only way a surplus liquid can leave a line; the planner adds units as needed.
- **Filling Unit**: bottles a fluid into a solid. A recipe like any other; the way a fluid product becomes storable.

Liquids and gases cannot be stored in the depot. A fluid target is therefore a rate someone must consume, and the planner says so.

## The depot

The depot is unbounded in the model. What the plan tracks instead is each item's net rate: positive accumulates, negative starves, zero balances. Accumulation at a Depot Loader is information; accumulation on a shared belt is an error, because the belt fills and stops its producer.

## Basements

A basement is a Core AIC Area: an outpost or a hub of one region. Its square grows with its level (Valley IV outposts 24×27, 32×32, 40×40; Wuling outposts 30×30, 40×40, 50×50; hub sizes unknown). Depot access differs by region: in Valley IV fixed Depot Bus segments sit on the square's edge at positions the dataset does not yet hold; in Wuling the player lays a Bus Port (4×4) and Bus Sections (4×8) inside the square, and loaders and unloaders must touch them. Wuling's machine set is a superset of Valley IV's; Valley IV has no fluids.

## Gas and activation

An environment recipe runs only inside the 13×13 zone of a **Gas Dispersing Unit** fed 6 per minute of the zone's gas (Inertgen for a stable environment, and so on); zones may not overlap. The two **Transmuting Units** run only while fed at least 6 per minute of their activation fluid (Liquid Xiranite, or Xiragen) and waste up to 30. The gas flag removes all of this from a plan.

## Power

The core supplies 200 power; machines draw their table value; pylons power a five-cell radius. The planner warns above the core budget and the verifier warns about a machine outside every pylon, both as warnings because the Automation-Core's own powered area is not modelled.

## Limits the game imposes

At most 128 pipe units in a basement. A blueprint holds at most 50×50 cells and 160 nodes, and blueprint share codes cannot be imported from outside the game, which is why the tool's output is a build guide cut into modules.
