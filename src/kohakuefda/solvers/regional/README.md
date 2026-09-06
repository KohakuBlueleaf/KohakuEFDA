# regional/

Seeded, coupled frontier construction with spatial/graph neighborhood reconstruction.
No spread seed is needed. Completed states use the same optional greedy compaction
as the baseline. Only the framework owns mutable physical state.

## Files

| File | Provides |
|---|---|
| `__init__.py` | Regional solver and validated policy defaults |
| `candidates.py` | Temporary clearance map and compatible-port-distance proposals |
| `search.py` | Overridable priority/insertion operators, missing-machine pressure, restarts and regional withdrawal/refill |

## Contracts

Construction prefixes have routes for all ready connections. `Builder.withdraw`
removes a proposed region atomically and repairs remaining ready routes; failure
restores the previous prefix. A best partial checkpoint is diagnostic, not a
published result. `finish()` publishes only complete geometry-checked routing.
Compaction never accepts a partial result. Rates are not an acceptance criterion.

The solver preserves the framework's logical connections. Load-balancing topology
belongs to planning/netlist construction, not this search. Port and route queries
provide physical proposals; they do not alter source allocations or demand.

All policy defaults live in `DEFAULTS`. `shrink_rounds=0` stops at first complete
construction. `seconds` and `max_actions` are common runtime settings, not policy
parameters. Regional execution is serial even if a caller requests more workers.
Use Studio's `regional` solver choice and JSON `solver_options` for policy overrides.

## Dependencies

- `kohakuefda.framework`, `kohakuefda.model.geometry`, `kohakuefda.model.solver`.
- `kohakuefda.solvers.baseline.shrink` for optional complete-state compaction.
- External: `numpy` for candidate filtering and scoring.
