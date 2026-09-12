# kohakuefda.physics

The Endfield physics pack: what the Core AIC Area grid means, stated to KohakuLayout
through its hooks. The pack takes no dataset; a scenario's footprints ride in the
problem's netlist library, its basement in the fabric and its params, its machine facts
in `attrs["endfield"]`. Every rule cites `.internal/game-knowledge/` by fact id.

| file | what |
|---|---|
| `__init__.py` | `EndfieldPhysics` (id `endfield`, version `1`), registered with the framework |
| `library.py` | the units per carrier (splitter, converger, bridge, control port; pipe units take the ground cell), the pylon footprint and its 12×12 emitter, run limits, the pipe-unit limit, the conduit link length |
| `fabric.py` | `fabric(params)`: the square plus its ring, layers `ground` and `sky`, carriers `belt` and `pipe` with their rates, regions `build`, `area`, `ring`, `bus_fixed`; `area_rect`, `entry_rect`, `slots_of`, `fixed_cells` read the params back; outside inputs enter on the sides `entry_sides` names (north and west by default) |
| `facts.py` | reading the flat `endfield` attrs: pin facts `pin:item:rate/min`, lane facts, slots `x:y:side`, fixed cells `x:y` |
| `carriers.py` | `EndfieldCarriers`: a wire shares a cell with its own carrier's unit, bridges cross, splitters and convergers branch, run limits with the carrier's splitter as the repeater (a junction ends a continuous conveyor, LOG-05); `BENT_CROSSINGS`, off, lets a lane start on a bridge where the crossed belt or pipe bends |
| `fields.py` | `EndfieldFields`: the `power` need and the pylon emitter under `PylonSweep`, a swept planner laid afresh after every placement: powered footprints in row order, each swept into the first group whose pylon windows still share a free square, one pylon per group on the first free square of its window inside the area, the occupancy read from the kernel as one grid and each window scanned at once (COV-01, COV-02, REG-03) |
| `boundaries.py` | `EndfieldBoundaries`: anchors for `edge`, `slot`, bus and zone groups, else the area; `brick_anchors` (a brick's anchors only where its back face can reach a part, seated from the back cells' offsets); `legal` for the area, every port's attach cell open with a cell its wire can arrive through (`approach_fault`), the border, the slots, bus seats and clusters, zone containment and overlap; pipes alone cross the ring and no logistics unit stands in it (`unit_region`, REG-03); `BRICK_SEAT` and `BRICK_SEAT_MIDDLE` carry DEP-18's seat count and middle cell; the anchor generators yield `(x, y, rot)` rows (`anchor_rows`), `anchors` wraps them; the approach check reads the ports through the cached `options_at` |
| `flow.py` | `EndfieldFlow`: the routed evaluator's hooks read from the flow facts (`role`, `pins`, `needs`, `makes`, `activation`, `accepts`, `filter`, a unit's `item`, the netlist's `links`): a crafter at the least-fed input, stalled under its activation, taking what its recipe consumes and making what its outlets accept; sources, entries and depot ports making their item at their rate; dumps and gas units taking at their rate; conduit inlets handing to their outlet; a converger with one input bringing what the outlet takes and with several each its capacity; control ports passing one item; the planned rate as each pin's demand; `evaluator` is `routed` and assessments do not run it |
| `rules.py` | the deck over a framework layout: area, belts in the ring, run length (a run ends at a unit of its own net, LOG-05), pipe units, the bus (parts in a cluster around a port, every grouped brick off a slot seated on a part or the fixed bus), the zones (grouped members inside their unit's zone, every environment machine inside some zone, zones apart), one Automation-Core, conduit links within reach, wiring that branches and merges only on junction units and ends only on ports |
| `objective.py` | `EndfieldObjective`: area and machine count |

Dependencies: `kohakulayout` (`ir`, `physics`); nothing else of the project.
