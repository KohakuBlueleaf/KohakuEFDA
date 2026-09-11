# kohakulayout.verify

Findings about a layout. Structural findings ask no physics; the runner then runs
every rule of the pack.

| file | what |
|---|---|
| `structural.py` | `geometry` (every `Layout.check` and `Layout.check_against` message), `missing` (unplaced cells), `unrouted` (nets without wires); `structural` is the three in order |
| `runner.py` | `run(world, layout, metrics)`: structural findings, `occupancy` (`kl.occupancy`: two occupants on one cell of one layer the pack's carriers do not let share; a unit carries wires across), `legal` (`kl.legal`: a placement the pack's boundaries refuse, asked of the whole layout), `uncovered` (`kl.field`: a placed cell's need no emitter unit reaches), the flow evaluator's findings when `physics.flow.evaluates`, then the pack's rules through `run_rules` |
| `report.py` | `report(assessment)`: verdict, metrics, findings as plain text |

## Dependencies

`kohakulayout.ir`, `kohakulayout.physics`.
