# kohakulayout.engine

What a solver runs in. The engine gives a solver budgets, rollback, assessment, progress
and checkpoints, and owns nothing about how to search.

| file | what |
|---|---|
| `context.py` | `Context`: problem, physics, world, seeded rng, budget, plugins, progress sink, `builder()`, `charge(units)` (the budget spent and `on_budget` told; the builder charges every operation through it), `attempt(fn, strict=True)` (a returned refusal rolls back; with `strict` so does the last refusal met), `snapshot`/`restore`, `assess`, `consider`/`accept`/`discard`, `frame`, `checkpoint`/`resume`, `gather`, `scope` |
| `builder.py` | `Builder`, the only door: place, place_instance, withdraw, route, unroute, reserve, marks, anchors, admits, first_open, diagnostic, finish |
| `budget.py` | `Budget(units, seconds)`: `charge` raising `BudgetExhausted` naming the knob, `limit` scopes, `remaining`, `exhausted` |
| `attempt.py` | `Attempt`, `Result`, `Block` |
| `assessment.py` | `metrics(world)` in `FRAMEWORK_METRICS` order and `assess(world, layout)` |
| `progress.py` | the `Event` envelope, `Sink` protocol, `NullSink`, `ListSink` (with a timestamp-free digest), `CallbackSink` |
| `checkpoint.py` | `Checkpoint` (run, seq, solver, params, seed, rng state, budget, layout, best), `save`, `load` |
| `workspace.py` | `Workspace(problem, physics, scale)`: an oversized board with the target in its middle, `overflow`, `project`, `publish` |
| `execution.py` | the execution slot: `InProcess`, `ProcessPool`, `make_execution(workers)` |
| `scopes.py` | `Scope(ctx, component, units)`: a phase name and an optional budget cap |
| `plugins/` | the plugin protocol, manager and built-ins (its own README) |

## Dependencies

`kohakulayout.errors`, `kohakulayout.ir`, `kohakulayout.physics`, `kohakulayout.state`, `kohakulayout.verify`.
