# solvers/

Concrete strategies over the framework's public Context. This package is an
application composition point, not imported by the framework or physical model.

## Files

| File | Provides |
|---|---|
| `__init__.py` | Application-visible SOLVERS catalog |
| `baseline/` | First-feasible spread and greedy shrink |
| `regional/` | Coupled frontier construction with regional reconstruction and optional greedy compaction |

## Dependencies

- `kohakuefda.framework`, `kohakuefda.model.solver`.
- External: `numpy` for regional candidate queries.
