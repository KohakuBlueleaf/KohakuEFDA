---
title: The native routing grid
summary: An optional Rust extension holds the two-layer routing grid and its A*; the package runs without it, a differential test holds the two to identical layouts, and it is worth about ten times the whole run.
tags:
  - dev
  - internals
  - performance
---

# The native routing grid

## What it is

`src/kohakuefda-rs/` is a PyO3 crate that compiles to `kohakuefda._native` and exports two
classes: `_Grid`, the occupancy of the two routing layers and the A\* over them, and `_State`,
its saved form. Python keeps every stage, every rule and every decision; Rust holds the cells
and walks them.

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

`kohakuefda.route.pathfinder.RouteGrid` is the proxy. It exposes the same API it always did
and forwards every change into `_Grid`; when the extension is not built it keeps the state in
its own dicts and runs `pathfinder.search`, the Python A\*, instead.

## Building it

The package's build backend is **setuptools**, so `pip install -e .` installs the Python
package and does not touch the crate. The extension is built separately, with maturin:

```bash
uv pip install -e ".[native]"     # installs maturin
maturin develop --release         # builds the crate into the active venv
```

Confirm it was picked up — this prints `True` only when the extension imported:

```bash
python -c "import kohakuefda.route.pathfinder as p; print(p.NATIVE)"
```

For a plain source build instead, `cargo build --release` and copy
`target/release/_native.dll` (`.so`, `.dylib`) next to the package as
`kohakuefda/_native.<abi>.pyd`. Nothing else changes: the package imports it if it is there.

### Two failures worth knowing

**`Both VIRTUAL_ENV and CONDA_PREFIX are set. Please unset one of them`** — maturin will not
guess which environment to install into. Unset one for the command:

```bash
unset CONDA_PREFIX && maturin develop --release
```

**`failed to copy … to _native.<abi>.pyd: os error 32`** (Windows) — a live Python process is
holding the old extension open, and Windows will not replace a loaded DLL. The layout search
runs worker processes; an interrupted run can leave one behind. Stop it and build again:

```powershell
Get-Process python | Where-Object { $_.Path -like "*KohakuEFDA*" } | Stop-Process -Force
```

An ABI-tagged file left over from an older build (`_native.cp313-win_amd64.pyd`) shadows the
plain one, so if a rebuild seems to have no effect, check which of the two is newer.

## What moved and what did not

| In Rust | Still in Python |
|---|---|
| Blocked, owned, unit, holder and reserved cells per layer, and their history | Which machine goes where, and why |
| The A\* with its crossing, reservation, unit and budget rules | The score and the searches over it |
| Whether a footprint fits, whether a pin still has an open port | The order machines are laid in |
| Where a pylon may stand | The group rules, the coverage grouping and the findings |
| The whole occupancy saved and restored, so an undone move costs a copy | The wires' own paths and the router's trees |

## Why it is held to the Python one

A mirror that is only ever read through itself cannot be witnessed, so `tests/test_native.py`
runs the same instance through both: 60 random grids of machines, lanes, units and
reservations × two sharing modes × two budgets, comparing the path each search returns, plus a
whole layout run with and without the extension, which must produce a byte-identical layout.
`cargo test` covers the search's own rules — crossings, units, reservations, budgets, forced
directions.

## What it is worth

`scenario_basic` (Hetonite 15/min, 31 machines), one worker, 120 search steps, same seed. Both
produce the same layout — 1368 cells of area, 626 lane cells — so this is pure speed:

| | Spread | Shrink | Total |
|---|---|---|---|
| Python | 97.63 s | 18.77 s | 116.40 s |
| Rust | 7.32 s | 3.57 s | **10.89 s** |

About **10.7× overall**: 13× on the search, where nearly all the time is A\*, and 5× on
shrinking, where each proposal is a whole layout rebuilt and rerouted. Without the extension a
real scenario is minutes rather than seconds, which is why it is worth building even though
the package runs happily without it.
