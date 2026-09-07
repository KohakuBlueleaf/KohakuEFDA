# solvers/

Concrete strategies over the framework's public Context. This package is an
application composition point, not imported by the framework or physical model.

## Files

| File | Provides |
|---|---|
| `__init__.py` | Application-visible SOLVERS extension catalog |
| `baseline/` | First-feasible spread and greedy shrink |
| `local/` | Matched HC/SA construction/improvement and experimental `hc-tree`/`sa-tree` structural variants |
| `regional/` | Coupled frontier construction with regional reconstruction and optional greedy compaction |

## Dependencies

- `kohakuefda.framework`, `kohakuefda.model.solver`.
- External: `numpy` for regional candidate queries.
