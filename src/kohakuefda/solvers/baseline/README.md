# baseline/

Construct a complete routed spread, then greedily compact it using public actions.
The solver owns traversal, gap/retry policy, batch winner selection and acceptance;
the framework owns physical changes, assessment, isolation and artifacts.

## Files

| File | Provides |
|---|---|
| `__init__.py` | Baseline strategy and validated defaults |
| `spread.py` | Seeded flow traversal, lattice, rotations and construction retries |
| `shrink.py` | First-improvement carve/press/nudge proposals |
| `parallel.py` | Seeded construction batches; selected snapshots imported without replay |

## Dependencies

- Public `kohakuefda.framework` services and `kohakuefda.model.solver` records.
- No direct Site/grid mutation or concrete routing implementation imports.
- External: none.
