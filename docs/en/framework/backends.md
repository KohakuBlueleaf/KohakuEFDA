---
title: Physical backend boundary
summary: Ownership of Python transactions, Site services, Rust kernels and compatibility checks.
tags: [framework, native, architecture]
---

# Physical backend boundary

## Python and Rust ownership

```text
Python solver                  strategy and private search history
      |
Context / Builder              immutable views and atomic candidate publication
      |
SiteBackend                    snapshots, scope, materialization, assessment
      |
Site + Router                  physical edits, route dependencies, port claims
      |
RouteGrid                      one selected occupancy backend per instance
      +---- Python reference
      `---- Rust Grid          flat occupancy arrays and A*
```

Rust has no second solver, objective or legality vocabulary. Its routing core is
under `src/kohakuefda-rs/route/`; PyO3 is isolated in `bindings.rs`. The extension
exports `BACKEND_API=1`, `_Grid` and `_State`. Solvers never call these directly.
Backend selection is per instance, so selecting the Python reference does not
mutate a process-global native flag or change another concurrent run.

## Snapshot correctness

Site snapshots include placements, chosen block ports, world pin tables, route
paths and branch/join attachments, router port claims/trees/forced state, and both
Python and native occupancy. Python history and wire-ID mappings are restored as
well. Cumulative attempt diagnostics and work counters are not rolled back.

Rust grid snapshots include their dimensions. Loading a checkpoint into a grid
of different dimensions raises ValueError before mutation. Native snapshots are
in-memory implementation details; portable checkpoints use the framework's
versioned JSON representation and can be reconstructed on either backend.

A framework candidate retains the exact emitted layout and placement artifact.
Import reconstructs backend routes, regenerates the physical layout and requires
that it matches, then runs the current assessment. Checkpoints are not trusted
proofs merely because they contain an Assessment record.

## Routing and coverage addons

`Runner(..., routing=object, coverage=object, objective=object)` injects already
built components. Default implementations live in `framework.backend`:

- `SiteRouting.name` and `__call__(site, required_wire_ids) -> bool` use the
  existing ordered router. It can rip dependent attachments but does not perform
  general blocker-directed search across unrelated connections.
- `SiteCoverage.name` and `__call__(site) -> (anchors, uncovered_ids)` use the
  existing pylon cover. The returned anchors are checked when materialized.
- `AreaWire.name` and `key(assessment)` provide the default ordering.

These are low-level trusted backend extension contracts. Unlike an ActionHandler,
a routing addon works directly on scratch Site geometry and must preserve all
unrelated semantic data. It must poll `site.check`, maintain grid/route agreement,
and never change the problem. The enclosing context owns rollback on failure,
exceptions and cancelled work, and rechecks the resulting geometry before
issuing a candidate. Use the Python implementation as the correctness reference.

The storage adapter is currently SiteBackend, not a universally pluggable native
world engine. The stable solver-facing contract is Context and the immutable
records. Replaceable routing, coverage and action implementations are working
slots; a different storage implementation needs an adapter satisfying that same
observable contract.

## Boundaries not yet implemented

- No resumable/pollable native A* search; cancellation is between routing calls.
- No general conflict-directed blocker selection or complete multi-net routing.
- No arbitrary recipe-mode or pipe-product-configuration edits.
- No source/sink reassignment; link requirements remain fixed in this version.
- No preservation certificate for rate-equivalence after rerouting; rates are
  rechecked explicitly, never assumed from a previously verified geometry.
- No solver-private exact-resume codec; checkpointing is restart-from-layout.

These are extension work, not silently enabled guarantees.

## Build and validate

```sh
source .venv/bin/activate
unset CONDA_PREFIX
maturin develop --release
cargo test
python -m pytest -q tests/test_framework.py tests/test_native.py
```

Native/Python tests compare concrete paths and reconstructed layouts. Transaction
tests exercise both backends, including another operation after rollback. Neither
backend's speed is accepted as a reason to weaken scope or evidence semantics.
