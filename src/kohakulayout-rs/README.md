# kohakulayout-rs

The native twin of KohakuLayout. Python is the ground truth; every function here reproduces
a Python function byte for byte and is held to it by `tests/kohakulayout/parity/`.

| path | what |
|---|---|
| `src/ir/model.rs` | every level as serde types with the same defaults pydantic dumps |
| `src/ir/rate.rs` | rates as normalised fractions, crossing JSON the way `str(Fraction)` writes them |
| `src/ir/json.rs`, `digest.rs` | canonical JSON (sorted keys, no whitespace, unicode kept) and its sha256 |
| `src/ir/geometry.rs`, `hier.rs`, `flatten.rs` | rotations, attach cells, rectangle covers; pins and footprints; the macro footprint; `flatten` |
| `src/text/kl.pest` | the grammar, mirroring `ir/text/kl.lark` rule for rule |
| `src/text/parser.rs`, `assemble.rs`, `writer.rs` | text to statements to levels, and levels to canonical text |
| `src/text/levels.rs` | the JSON boundary: parse, write, flatten, canonical, digest |
| `src/kernel/grid.rs` | the occupancy grid with `PyKernel`'s exact `save()` bytes |
| `src/kernel/astar.rs` | the path search over the grid, the pack's answers handed in as tables; `pathfinder.find`'s twin |
| `src/pyo3_module.rs` | `kohakulayout_rs`: `parse_kl`, `write_kl`, `flatten`, `canonical`, `digest`, `Grid` |

## Building

```
cd src/kohakulayout-rs
VIRTUAL_ENV=../../.venv maturin develop --release
```

`KOHAKULAYOUT_BACKEND=python` forces the Python path everywhere; `native` makes a missing
module an error. `kl_check.py bench` requires the module.
