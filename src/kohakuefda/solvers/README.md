# solvers/

The project's solver on KohakuLayout: `endfield.guided`, the studio's `guided`. It imports
the framework and the pack's vocabulary; nothing imports it but the layout settings.

`guided` seeds a layout, then runs the framework's local search (`climb` or `anneal`
acceptance) over free coordinates. The seed is the lines shape (`seed_kind="lines"`),
falling back to the regional construction when the lines do not land within
`seed_units` actions. Repair and repacking rank anchors by a distinct-port assignment
against the lane router's targets; every `reseat_every` proposals a depot brick moves to
another legal slot, alone or with one partner; `adaptive_moves` draws the ordinary
operators by their recent reward per charged work. The defaults are the measured study
profile (`docs/en/dev/solvers.md`).

## Files

| File | Description |
|---|---|
| `__init__.py` | Registers the solver on import; `SOLVER_IDS` |
| `guided.py` | `GuidedLayout` (id `endfield.guided`): the framework's local params with `OVERRIDES`, the search settings of `GUIDED`, `acceptance`, `seed_kind`, `seed_gap`, `seed_units`; the regional seed ranks with `REGIONAL_SEED` |
| `search.py` | `embed` (force-directed lane-graph layout), `EndfieldProposals` (lane-router targets, embedding pull, depot lattice, footprint-only clearance), `EndfieldSearch` (the regional seed, lane neighbours, unwired cells first, `RESEATED` brick constraints), `GuidedProposals` (contact scoring), `GuidedSearch` (repair around recently refused endpoints); `DEFAULTS`, `GUIDED` |
| `lines/` | The lines seed; see its README |

## Dependencies

- `kohakulayout.solvers` (`LocalSolver`, `PARAMS`, `Trajectory`, `Search`, `Proposals`, `ContactProposals`, `legalize`, `register`).
- `kohakuefda.physics` (`boundaries`, `fabric`, `facts`) and `kohakuefda.layout.router` (`LanePolicy`, `lane_ends`).
