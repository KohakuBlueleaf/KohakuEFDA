# layout/

Physical geometry, groups, occupancy-facing placement, assembly and stage adapters.
Search strategies live in `solvers/`; safe solver services live in `framework/`.
The baseline constructs a routed spread and greedily compacts it through Context.

## Files

| File | Description |
|---|---|
| `geometry.py` | Footprints and world ports |
| `connect.py` | Directed connectivity of emitted layouts |
| `fragments.py` | Translate, rotate and place fragments |
| `depot_via.py` | Bus slots, attachment and depot capacity arithmetic |
| `coverage.py` | Pylon coverage and zone geometry |
| `place.py` | Mutable backend blocks and placement artifact conversion |
| `board.py` | Basement, ring, fixed cells, slots and independently retained entry border |
| `groups.py` | Mandatory group constraints |
| `site.py` | Coupled placement/routing, batched footprint updates, unique wired-pin checks and clipped occupied bounds |
| `engine.py` | Solver composition, Runner adapter and target-valid versus workspace-only final evidence |
| `assemble.py` | Emitted layout and routing pins with immutable cached port-access geometry |
| `chunk.py` | Blueprint module partitioning |
| `stages.py` | Four stage APIs and strict shared/solver parameter validation before execution |
| `pipeline.py` | Scenario-to-artifacts orchestration and recorded frames |

## Dependencies

- Physical modules: `model`, `route`, existing geometry collaborators.
- Stage adapters: `framework`, `solvers`, `plan`, `flow`, `verify`.
- External: `numpy`.
