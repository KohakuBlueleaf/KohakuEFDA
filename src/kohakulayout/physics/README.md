# kohakulayout.physics

The physics protocol: what a project states about its game, as eight modules of hooks
with defaults. A pack subclasses `BasePhysics` and overrides what its game has.

## Files

| file | what it is |
|---|---|
| `protocol.py` | the data shapes (`Occupant`, `CrossingRule`, `JunctionRule`, `Reach`, `Emitter`, `Anchor`, `UnitPlacement`) and the hook protocols |
| `base.py` | `BasePhysics`: every default; `fabric` and `library` are required |
| `carriers.py` | stage 1 defaults: exclusive cells, no crossing, no junction, no run limit |
| `fields.py` | stage 2 defaults, `GreedyCover, KindCover (one planner per field kind, greedy for the rest)` (the cover planner slot's occupant), reach helpers |
| `boundaries.py` | stage 3 defaults: free anchors in the build region, nothing extra illegal, edge entries |
| `flow.py` | stage 4 defaults: even split, proportional capped merge |
| `rules.py` | `FunctionRule` and `run_rules` |
| `objective.py` | `DefaultObjective` and the weighted `energy` |
| `diagnose.py` | the generic diagnostic chain |
| `registry.py` | pack registration and entry-point discovery; an unknown pack is named |

## Dependencies

- `kohakulayout.ir`, `kohakulayout.errors`. Imported by `state` and everything above.
