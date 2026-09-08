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
cd src/kohakulayout-rs
VIRTUAL_ENV=../../.venv maturin develop --release
```

Python 3.14 needs pyo3 0.26 or newer, which the crate pins. Without the module the
framework runs unchanged on its Python paths.

## How it is used

| Python entry point | what the twin does | fallback |
|---|---|---|
| `parse_text` | parses the text and returns every level as JSON; Python rebuilds the models | the Lark parser |
| `write` / `Level.text()` | writes canonical text from the level's JSON | the Python writer |
| `Level.digest()` | canonicalises (flattening a netlist or problem) and hashes | `digest_of(canonical())` |
| `Netlist.flatten()` | flattens through the twin | the Python flatten |
| `make_kernel("auto")` | the `Grid` handle behind the `Kernel` protocol | `PyKernel` |

`KOHAKULAYOUT_BACKEND=python` disables the twin everywhere; `native` makes a missing module
an error, so a parity failure can be reproduced on either side.

## Parity

- Every `.kl` fixture: the same levels JSON, the same text, the same digest, the same flat form.
- Sixty seeded random problems and layouts from the test generator: the same on both sides.
- The kernel: random operation sequences and every recorded gates run replayed into both
  kernels give identical `save()` bytes and identical query answers.

`python scripts/dev/kl_check.py bench` requires the module, runs the parity suite, then
compares every bench against `tests/kohakulayout/bench/ledger.json`.
