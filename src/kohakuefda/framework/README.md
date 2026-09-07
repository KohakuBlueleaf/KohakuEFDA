# framework/

Solver-independent execution and transactional physical-layout services. The public
entry point is `solve(problem, solver, ...)`; the baseline is an injected client.
Manual and contracts: `docs/en/framework/`.

## Files

| File | Provides |
|---|---|
| `__init__.py` | Public exports |
| `problem.py` | Immutable domain capture and content identities |
| `config.py` | Strict settings and application-owned catalog with parameter types and parallel capability metadata |
| `control.py` | Global work/time budgets, nested local work allowances, cancellation and errors |
| `actions.py` | Workspace/handler protocols and relocate/rebuild/reroute handlers |
| `backend.py` | Site adapter, immutable port/tree endpoint queries, routing/coverage injection and snapshot codec |
| `assessment.py` | Materialization, optional metric-only rejection, mandatory candidate checks and separate rate evidence |
| `context.py` | Builder with assessed multi-action transactions and expiry-safe rollback, atomic withdrawal/refill, scoped scratch actions, revision-safe publication events and best archives |
| `execution.py` | Isolated batch workers, optional progress IPC and cleanup; no winner-selection policy |
| `progress.py` | Common sampled frame schema, retained-current/best evidence and mandatory milestones |
| `runtime.py` | Solver protocol, Runner and solve lifecycle |
| `checkpoint.py` | Versioned JSON routed-seed save/load |
| `scopes.py` | Component membership, footprint union and boundary-link queries |
| `workspace.py` | Isolated expanded search, original entry/slot geometry, shared budgets, overflow metrics and strict target projection |

## Progress frames

All builtin solvers send self-contained sampled `build`/`improve` frames through
`Context.frame`. `frame_schema=1` includes materialized layout, grid, search area,
original `target_area`, fixed cells/slots, assessed terms, domain, phase and work.
`best` is separate assessed metadata; it never substitutes best geometry for the
current frame. Workspace routing does not set target `clean`/`evidence.routed`.

`frame_every=1` samples each safe solver boundary; N samples every N calls with a
one-second elapsed fallback at safe boundaries (`progress.FRAME_SECONDS`). Zero
suppresses periodic samples, not start/expansion/construction/stop milestones.
Snapshots do not show intermediate illegal routing trials. Emission costs count
against elapsed budgets; it consumes no proposal RNG or action/route credits.
Parallel baseline workers stream independently labeled snapshots while retaining
deterministic input-order result selection. Worker counters remain separate from
completed-batch global work. Final/cancel/error frames retain available evidence.

## Dependencies

- `kohakuefda.model`, physical modules of `layout`, `route`, `flow`, `verify`.
- Never `kohakuefda.solvers`, `cli`, `serve`, or `layout.engine/stages`.
- External: `pydantic` for checkpoint decoding; optional native grid through `route`.
