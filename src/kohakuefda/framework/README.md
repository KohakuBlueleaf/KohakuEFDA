# framework/

Solver-independent execution and transactional physical-layout services. The public
entry point is `solve(problem, solver, ...)`; the baseline is an injected client.
Manual and contracts: `docs/en/framework/`.

## Files

| File | Provides |
|---|---|
| `__init__.py` | Public exports |
| `problem.py` | Immutable domain capture and content identities |
| `config.py` | Strict settings and application-owned extension catalog |
| `control.py` | Work/time budgets, cancellation and errors |
| `actions.py` | Workspace/handler protocols and relocate/rebuild/reroute handlers |
| `backend.py` | Site adapter, immutable queries, routing/coverage injection and snapshot codec |
| `assessment.py` | Materialization, optional metric-only rejection, mandatory candidate checks and separate rate evidence |
| `context.py` | Builder, scoped scratch actions, revision-safe publication and best archives |
| `execution.py` | Isolated batch workers and cleanup; no winner-selection policy |
| `runtime.py` | Solver protocol, Runner and solve lifecycle |
| `checkpoint.py` | Versioned JSON routed-seed save/load |
| `scopes.py` | Component membership, footprint union and boundary-link views |

## Dependencies

- `kohakuefda.model`, physical modules of `layout`, `route`, `flow`, `verify`.
- Never `kohakuefda.solvers`, `cli`, `serve`, or `layout.engine/stages`.
- External: `pydantic` for checkpoint decoding; optional native grid through `route`.
