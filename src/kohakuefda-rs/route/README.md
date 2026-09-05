# route/

Solver-independent native occupancy and A*. Python bindings live one level up;
this module has no layout-search strategy.

## Files

| File | Provides |
|---|---|
| `mod.rs` | Kernel and test module exports |
| `core.rs` | Flat two-layer grid, crossing rules and path search |
| `tests.rs` | Real-grid route behavior tests |

## Dependencies

- Rust standard library only.
