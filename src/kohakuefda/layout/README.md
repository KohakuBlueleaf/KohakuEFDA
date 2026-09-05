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
| `site.py` | Backend-owned placement/routing state and complete snapshots |
| `engine.py` | Compatibility/composition adapter to framework Runner and solver catalog |
| `assemble.py` | Blocks/support to emitted layout and routing pins |
| `chunk.py` | Blueprint module partitioning |
| `stages.py` | Four stage APIs and parameter validation |
| `pipeline.py` | Scenario-to-artifacts orchestration and recorded frames |

## Dependencies

- Physical modules: `model`, `route`, existing geometry collaborators.
- Stage adapters: `framework`, `solvers`, `plan`, `flow`, `verify`.
- External: `numpy`.
