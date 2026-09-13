---
title: The KohakuLayout native twin
summary: A Rust crate reproduces the framework's text form, canonical JSON, flatten, digest and occupancy kernel byte for byte; Python stays the ground truth, the twin is used when built and agrees.
tags:
  - dev
  - kohakulayout
  - native
---

# The KohakuLayout native twin

`src/kohakulayout-rs/` builds the Python module `kohakulayout_rs`. It holds nothing the
Python package does not also implement: the `.kl` parser and writer, canonical JSON and its
sha256 digest, netlist flattening, and the per-layer occupancy grid. Every function is
checked against its Python original by `tests/kohakulayout/parity/`.

## Building

```
maturin develop --release    # at the repository root, inside the venv
```

The crate's `Cargo.toml` sits at the root beside `pyproject.toml`; its sources are
`src/kohakulayout-rs/src/`.

The crate needs rustc 1.88 or newer (`rust-version` in `Cargo.toml`); Python 3.14 needs pyo3 0.26 or newer, which the crate pins. Without the module the
framework runs unchanged on its Python paths.

## How it is used

| Python entry point | what the twin does | fallback |
|---|---|---|
| `parse_text` | parses the text and returns every level as JSON; Python rebuilds the models | the Lark parser |
| `write` / `Level.text()` | writes canonical text from the level's JSON | the Python writer |
| `Level.digest()` | canonicalises (flattening a netlist or problem) and hashes | `digest_of(canonical())` |
| `Netlist.flatten()` | flattens through the twin | the Python flatten |
| `make_kernel("auto")` | the `Grid` handle behind the `Kernel` protocol | `PyKernel` |
| `pathfinder.find` | the A* over a native grid, with the pack's crossing, sharing and reservation answers handed in as tables built once per search; the grid counts its mutations (`generation`) and the layer classified for one rules text is kept while that count stands | the Python search |

`KOHAKULAYOUT_BACKEND=python` disables the twin everywhere; `native` makes a missing module
an error, so a parity failure can be reproduced on either side.

## Parity

- Every `.kl` fixture: the same levels JSON, the same text, the same digest, the same flat form.
- Sixty seeded random problems and layouts from the test generator: the same on both sides.
- The kernel: random operation sequences and every recorded gates run replayed into both
  kernels give identical `save()` bytes and identical query answers.
- The search: every path search of three seeded gates runs answers the same on both sides,
  cells, cost, crossings, rips and displaced emitters, a crossing on the path's own start
  or end cell included.

`python scripts/dev/kl_check.py bench` requires the module, runs the parity suite, then
compares every bench against `tests/kohakulayout/bench/ledger.json`.

The crate's search runs on flat arrays indexed by cell and direction, classifies every
cell of the layer once per search (closed, priced, under a unit, held by which wires) with
the rules' net and unit names turned into indices, keeps the last rules it parsed and the
walls registered per key, weighs its heuristic in step costs, and prunes past the detour
the rules set; the Python search stays the reference and the parity tests hold them to one
answer. The rules themselves come from the world's wires, units and reservations, not from
a scan of the cells.
