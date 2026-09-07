# layout/

Physical geometry, groups, occupancy-facing placement, assembly and stage adapters.
Search strategies live in `solvers/`; safe solver services live in `framework/`.
The default layout stage runs standard `hc` on the native backend for 600 seconds,
with seed 0, no action cap, and construction/improvement caps of 1,000,000 each.
HC's `until_budget=true` makes the time budget authoritative while both phases are
enabled. A zero phase cap skips that phase; it does not mean unlimited search.
Library solver defaults remain independently configurable. The baseline is still
available explicitly and constructs a routed spread before greedy compaction.

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
