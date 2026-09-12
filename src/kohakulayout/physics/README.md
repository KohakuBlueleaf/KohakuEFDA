# kohakulayout.physics

The physics protocol: what a project states about its game, as eight modules of hooks
with defaults. A pack subclasses `BasePhysics` and overrides what its game has.

## Files

| file | what it is |
|---|---|
| `protocol.py` | the data shapes (`Occupant`, `CrossingRule`, `JunctionRule`, `Reach`, `Emitter`, `Anchor`, `UnitPlacement`, `Made`, `Mix`) and the hook protocols; `CrossingRule.bent` lets the crossed wire turn on the cell |
| `base.py` | `BasePhysics`: every default; `fabric` and `library` are required |
| `carriers.py` | stage 1 defaults: exclusive cells, no crossing, no junction, no run limit |
| `fields.py` | stage 2 defaults, `GreedyCover, KindCover (one planner per field kind, greedy for the rest)` (the cover planner slot's occupant: the nearest free anchor over the need's bounding box plus the reach, off every open attach cell while one exists), reach helpers (`reach_cells` reads an emitter's reach once and keeps the shifted squares and masks it hands out) |
| `boundaries.py` | stage 3 defaults: free anchors in the build region, nothing extra illegal, edge entries; `anchor_rows`, the anchors as `(x, y, rot)` rows |
| `flow.py` | stage 4 defaults: even split, proportional capped merge; the routed hooks: a commodity per source pin, every pin accepting its capacity, no production of its own, the acceptance-capped even share, a merge letting each input fill the outlet, every commodity passing every unit, no links |
| `rules.py` | `FunctionRule` and `run_rules` |
| `objective.py` | `DefaultObjective` and the weighted `energy` |
| `diagnose.py` | the generic diagnostic chain |
| `registry.py` | pack registration and entry-point discovery; an unknown pack is named |

## Dependencies

- `kohakulayout.ir`, `kohakulayout.errors`. Imported by `state` and everything above.
