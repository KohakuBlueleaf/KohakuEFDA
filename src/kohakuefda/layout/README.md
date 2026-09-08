# layout/

Physical geometry, the board, blocks, the stage's settings and solver table, chunking,
the stages and the pipeline. The layout stage is a consumer of KohakuLayout: it turns
the netlist into a framework problem (`synth/`), runs the framework solver the project
name maps to, and translates the layout back. The default stage runs `hc` (the
framework's `climb`) on the `auto` kernel for 600 seconds with seed 0; `seconds` and
`max_actions` both at 0 stop after `DEFAULT_UNITS` charged actions.

## Files

| File | Description |
|---|---|
| `geometry.py` | Footprints and world ports |
| `connect.py` | Directed connectivity of emitted layouts |
| `fragments.py` | Translate, rotate and place fragments |
| `depot_via.py` | Bus slots, attachment and depot capacity arithmetic |
| `coverage.py` | Pylon coverage and zone geometry |
| `place.py` | `Block` (a cell's size, ports and anchor) and the placement artifact conversion |
| `board.py` | Basement, ring, fixed cells, slots and independently retained entry border |
| `config.py` | `settings_of` (overrides typed by their defaults, unknown names refused), `Entry` and `Catalog` (the studio's solver table), `ConfigurationError` |
| `engine.py` | The stage's flat settings, the project's solver names over the framework's solvers, typed solver options, the budget, the studio's catalogue |
| `chunk.py` | Blueprint module partitioning |
| `stages.py` | Four stage APIs; the layout stage runs the framework on the synth's problem and translates the layout back |
| `pipeline.py` | Scenario-to-artifacts orchestration and recorded frames |

## Dependencies

- Physical modules: `model`, `route`, existing geometry collaborators.
- Stage adapters: `synth`, `plan`, `flow`, `verify`, `kohakulayout` (`engine`, `pipeline`, `solvers`).
- External: `numpy`.
