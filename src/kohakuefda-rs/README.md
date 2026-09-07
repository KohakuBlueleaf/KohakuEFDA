# Native physical kernels

Rust accelerates solver-independent routing mechanisms, not search policy.
Python Context/SiteBackend owns transactions, assessment and solver lifecycle.
Build with `.venv` active and `CONDA_PREFIX` unset: `maturin develop --release`.

## Files

| File | Provides |
|---|---|
| `lib.rs` | PyO3 extension registration, BACKEND_API version |
| `bindings.rs` | Python adapter, batched occupancy queries, _Grid and dimension-checked _State snapshots |
| `route/` | Grid/occupancy/A* implementation and unit tests |

## Dependencies

- `pyo3` at the binding boundary.
- Routing kernels have no Python or solver dependencies.
- Behavioral parity tests: `tests/test_native.py`, `tests/test_native_queries.py`, `tests/test_framework.py`.
- Additive batch queries retain backend API 1; Python falls back when a method is absent.
