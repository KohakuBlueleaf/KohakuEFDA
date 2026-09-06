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
| `board.py` | Basement, ring, fixed cells and slots |
| `groups.py` | Mandatory group constraints |
| `site.py` | Backend-owned placement/routing state, complete snapshots and build-area-clipped occupied bounds |
| `engine.py` | Validated solver composition, Runner adapter and structured final search outcome |
| `assemble.py` | Blocks/support to emitted layout and routing pins |
| `chunk.py` | Blueprint module partitioning |
| `stages.py` | Four stage APIs and strict shared/solver parameter validation before execution |
| `pipeline.py` | Scenario-to-artifacts orchestration and recorded frames |

## Dependencies

- Physical modules: `model`, `route`, existing geometry collaborators.
- Stage adapters: `framework`, `solvers`, `plan`, `flow`, `verify`.
- External: `numpy`.
