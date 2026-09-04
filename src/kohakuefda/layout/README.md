# layout/

Geometry of a solution in world cells: footprints and world ports of placed
things, which port each belt or pipe segment leaves from and arrives at,
fragment moves, depot access and bus arithmetic, the pylon cover, blocks, the
board, the group rules, the live site where machines and their wires share one
grid, the spread that lays a whole layout out at once, the engine, assembly,
chunking, the four stages and the scenario → layout pipeline.

Placing and routing are one operation. `Site.place` is the only way a machine
enters a layout: it rips the wires its footprint would cover, puts the machine
down, routes every wire whose two ends are now placed, and undoes all of it if
any of them has no path — so a position that cannot be wired never exists.

`Spread` uses nothing else. Machines go into the squares of a lattice whose step
is the widest of them plus a pylon, so each stands alone with a corridor round
it; they are taken in the order the flow visits them and the squares in a
serpentine. A lattice either comes out whole — every machine standing, every
lane running — or it is thrown away and laid again from a different order, which
costs a few hundredths of a second. Nothing is ever moved aside to make room, so
there is no arrangement the search can wreck to reach another.

`Shrink` then takes the room back out. It only ever *removes* space — a line nothing
stands on, a whole side pressed to a wall, one machine pulled a cell toward what it
feeds — and keeps a proposal only when the layout still stands whole and is smaller.
So it cannot strand a machine or a lane: the worst it does is find nothing and stop.

## Files

| File           | Description                                                        |
| -------------- | ------------------------------------------------------------------ |
| `geometry.py`  | `footprint`, `machine_footprint`, `unit_footprint`, `WorldPort`, `machine_ports`, `unit_ports` |
| `connect.py`   | `Connectivity`: segment → source OUT port and target IN port, direction-aware, direct links, outside inputs |
| `fragments.py` | `translate`, `rotate` (whole fragment, machines and pins), `fragment_layout`, `place` |
| `depot_via.py` | `Slot`, `fixed_slots` (Valley IV brick slots in square coordinates), `brick_rotation`, `chain_capacity` and `sections_needed` (bricks a chain of parts seats), `laid_limits`, `io_budget`, `via_depot_ok`, `BUS_PORT`, `BUS_SECTION` |
| `coverage.py`  | `cover` (greedy pylon cover over free anchors, numpy), `coverage_rect`, `covered`, `zone_rect`, `inside`, `overlaps` |
| `place.py`     | `Block` (a cell at an anchor and rotation with a chosen port per pin, its group, world pins, footprint cells, machine rects), `touching`, `apply_positions`, `placement_of`, `catalogue_of` |
| `board.py`     | `Board` and `board_of`: square, ring, fixed bus cells and brick slots in grid coordinates |
| `groups.py`    | `back_cells`, `bus_faults`, `zone_faults`, `zone_of`, `faults`: what the game binds together and how far a placement is from obeying it |
| `site.py`      | `Site`: blocks, one routing grid and the router over it; `place` and `remove`, `wire_up`, `closes_a_port`, `snapshot`/`restore`, `occupied`, `bbox`, `faults`, `power` and `pylons`, `cost`, and the candidate anchors — `facing_anchors` (a port within reach of a partner's), `group_anchors`, `frontier_anchors`, `every_anchor` |
| `spread.py`    | `Spread`: `rank` and `order` (the flow walked chain by chain, each group whole), `clearance` and `envelope` (free cells derived per edge from where the wired ports are), `pitch` and `squares` (the lattice, in a serpentine), `settle`, `stand`, `lay`, `rebuild`, `frame`, and `run`, the restart search that keeps the first whole lattice |
| `shrink.py`    | `Shrink`: `measure` (area then lane cells), `carve` (delete a line nothing stands on), `press` (slide a whole side to a wall), `nudge` (one machine one cell toward what it is wired to), `apply`, `run` |
| `engine.py`    | `LAYOUT_DEFAULTS`, `Engine` (`attempt` and its rounds of searches, `islands`, `best_of`, `run`, `rank`, `build_layout`, `terms_of`, `fits`, `shortfalls`, frames), `_island` (one search per process), `EngineResult`, `LayoutError` |
| `assemble.py`  | `assemble` placed blocks and pylons into a `Layout` with its area, `world_pins`, `WorldPin` |
| `chunk.py`     | `chunk`: blueprint-sized modules with a build order                |
| `stages.py`    | `STAGES`, `DEFAULTS`, `params_of`, `blocks_of`, and the stage functions `plan_stage`, `netlist_stage`, `layout_stage`, `verify_stage` |
| `pipeline.py`  | `layout_scenario`: every stage in one call; `LayoutResult` with the recorded frames |

## Dependencies

- `kohakuefda.model`, `kohakuefda.flow`, `kohakuefda.verify`, `kohakuefda.route`, `kohakuefda.plan`
- External: `numpy`
