# kohakulayout.pipeline

| file | what |
|---|---|
| `passes.py` | `PassManager(passes)`: ordered passes over a `Problem`, each followed by `verify`; the `PASSES` registry with `flatten` and `check` |
| `solve.py` | `solve(problem, solver, seed, budget, params, plugins, progress, router, kernel, checker, passes) -> Result` (outcome, best layout, its assessment, checkpoints, events, the context) |

## Dependencies

`kohakulayout.ir`, `kohakulayout.engine`, `kohakulayout.solvers`.
