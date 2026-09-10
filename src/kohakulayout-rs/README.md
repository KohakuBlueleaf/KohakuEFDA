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
| `src/kernel/astar.rs` | the path search over the grid, the found path and the classified layer it takes, with the net's own crossable lane cells (`own`) and the sources' order passed per search, f32 cost sums when the rules set `float_scale`, no end on a crossing when they say so; `pathfinder.find`'s twin |
| `src/kernel/classify.rs` | the tables one search reads: the rules as handed in, their names as indices, a layer's cells classified once per grid state and priced for entry |
| `src/pyo3_module.rs` | `kohakulayout_rs`: `parse_kl`, `write_kl`, `flatten`, `canonical`, `digest`, `Grid` |

## Building

```
cd src/kohakulayout-rs
VIRTUAL_ENV=../../.venv maturin develop --release
```

`KOHAKULAYOUT_BACKEND=python` forces the Python path everywhere; `native` makes a missing
module an error. `kl_check.py bench` requires the module.
