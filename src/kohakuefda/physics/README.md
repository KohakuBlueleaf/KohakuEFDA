# kohakuefda.physics

The Endfield physics pack: what the Core AIC Area grid means, stated to KohakuLayout
through its hooks. The pack takes no dataset; a scenario's footprints ride in the
problem's netlist library, its basement in the fabric and its params, its machine facts
in `attrs["endfield"]`. Every rule cites `.internal/game-knowledge/` by fact id.

| file | what |
|---|---|
| `__init__.py` | `EndfieldPhysics` (id `endfield`, version `1`), registered with the framework |
| `library.py` | the units per carrier (splitter, converger, bridge; pipe units take the ground cell), the pylon footprint and its 12×12 emitter, run limits, the pipe-unit limit |
| `fabric.py` | `fabric(params)`: the square plus its ring, layers `ground` and `sky`, carriers `belt` and `pipe` with their rates, regions `build`, `area`, `ring`, `bus_fixed`; `area_rect`, `entry_rect`, `slots_of`, `fixed_cells` read the params back; outside inputs enter on the sides `entry_sides` names (north and west by default) |
| `facts.py` | reading the flat `endfield` attrs: pin facts `pin:item:rate/min`, lane facts, slots `x:y:side`, fixed cells `x:y` |
| `carriers.py` | `EndfieldCarriers`: a wire shares a cell with its own carrier's unit, bridges cross, splitters and convergers branch, run limits with the carrier's splitter as the repeater (a junction ends a continuous conveyor, LOG-05); `BENT_CROSSINGS`, off, lets a lane start on a bridge where the crossed belt or pipe bends |
| `fields.py` | `EndfieldFields`: the `power` need and the pylon emitter under the framework's greedy cover |
| `boundaries.py` | `EndfieldBoundaries`: anchors for `edge`, `slot`, bus and zone groups, else the area; `legal` for the area, every port's attach cell open with a cell its wire can arrive through (`approach_fault`), the border, the slots, bus seats and clusters, zone containment and overlap; pipes alone cross the ring; `BRICK_SEAT` and `BRICK_SEAT_MIDDLE` carry DEP-18's seat count and middle cell |
| `flow.py` | `EndfieldFlow`: even splits, stateful merges, the planned rate as each pin's demand; no evaluation (the project's evaluator stays the oracle) |
| `rules.py` | the deck over a framework layout: area, belts in the ring, run length, pipe units, the bus, the zones; a run ends at a unit of its own net (LOG-05) |
| `objective.py` | `EndfieldObjective`: area and machine count |

Dependencies: `kohakulayout` (`ir`, `physics`); nothing else of the project.
