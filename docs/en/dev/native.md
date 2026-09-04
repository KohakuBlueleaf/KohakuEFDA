---
title: The native routing grid
summary: An optional Rust extension holds the two-layer routing grid and its A*; the package runs without it, a differential test holds the two to the same paths, and it makes a layout run about four times faster.
tags:
  - dev
  - internals
  - performance
---

# The native routing grid

## What it is

`src/kohakuefda-rs/` is a PyO3 crate that compiles to `kohakuefda._native` and exports one class,
`_Grid`: the occupancy of the two routing layers and the A* over them. Python keeps every stage,
every rule and every decision; Rust holds the cells and walks them.

```
Cargo.toml                        lib name "_native", path src/kohakuefda-rs/lib.rs
rustfmt.toml                      cargo fmt settings
src/kohakuefda-rs/
    lib.rs                        module declarations and the #[pymodule]
    route/
        mod.rs                    what the subsystem is
        core.rs                   Grid, Cells, Search, astar — no Python in them
        python.rs                 the _Grid and _State bindings, register_route_types
        tests.rs                  cargo test over core
src/kohakuefda/_native.pyi        type stubs for the compiled module
```

`kohakuefda.route.pathfinder.RouteGrid` is the proxy. It exposes the same API it always did and
forwards every change into `_Grid`; when the extension is not built it keeps the state in its own
dicts and runs `pathfinder.search`, the Python A*, instead.

## Building it

```
pip install -e .[native]      # or: pip install maturin
maturin develop --release
```

or, for a source checkout, `cargo build --release` and copy `target/release/_native.dll`
(`.so`, `.dylib`) next to the package as `_native.<abi>.pyd`. Nothing else changes: the package
imports it if it is there.

## What moved and what did not

| In Rust | Still in Python |
|---|---|
| Blocked, owned, unit, holder and reserved cells per layer, and their history | Which machine goes where, and why |
| The A* with its crossing, reservation and budget rules | The cost function and the moves |
| Whether a footprint fits, whether a pin still has an open port | The order machines are placed in |
| Where a pylon may stand and which machines one can serve | The group rules and the findings |
| The whole occupancy saved and restored, so an undone move costs a copy | The wires' own paths and the router's trees |

## Why it is held to the Python one

A mirror that is only ever read through itself cannot be witnessed, so `tests/test_native.py`
runs the same instance through both: 60 random grids of machines, lanes, units and reservations
× two sharing modes × two budgets, comparing the path each search returns, plus a whole layout
run with and without the extension, which must produce a byte-identical layout. `cargo test`
covers the search's own rules — crossings, units, reservations, budgets, forced directions.

## What it is worth

`scenario_basic` (Hetonite 15/min, 31 machines, 39 lanes), construction plus 800 improvement
steps, same seed, same resulting cost of 2190:

| | Construct | Improve (800) | Total |
|---|---|---|---|
| Python | 1.46 s | 6.00 s | 7.46 s |
| Rust | 0.28 s | 1.35 s | **1.63 s** |

A* was about 95 % of a run before the port and is around 6 % after it. What is left is the
Python side of snapshot and restore, the wire paths, and the candidate generation.
