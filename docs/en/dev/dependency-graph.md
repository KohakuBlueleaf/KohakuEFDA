---
title: Dependency graph
summary: Domain mechanisms, framework services and solver policy have one-way imports.
tags: [dev, internals, architecture]
---

# Dependency graph

Arrows mean imports; callbacks and injected implementations do not reverse them.

```text
cli / serve / scripts
       |
       v
layout stages / pipeline / engine (application composition)
       |                       |
       v                       v
solvers catalog          framework runtime
       |                       |
       +----------+------------+
                  v
       framework Context / services
                  |
                  v
       framework SiteBackend / assessment
                  |
                  v
       physical layout / route / flow / verify
                  |
                  v
                model
```

- `model` imports no solver or framework modules; its solver records are data only.
- `data` imports domain records, never layout strategies.
- `plan` and geometry-free flow arithmetic remain upstream of physical layout.
- `layout/geometry`, `connect`, `depot_via`, `coverage` provide world operations.
- `verify/rules` and `flow/evaluate` use those physical operations, not solvers.
- `route/router` uses assembled pins and the grid; `layout/site` owns physical edits.
- `framework` adapts Site, materializes actual layouts and invokes shared checks.
  It imports no concrete solver or application module.
- `solvers` uses public Context, Builder, Action and immutable records. It does not
  manipulate Site or the native grid directly. `regional` uses candidate queries
  and construction withdrawal; its optional compaction reuses `baseline.shrink`.
  `local` supplies HC/SA policy over regional insertion/region helpers and builtin
  actions; it does not use regional's best-prefix loop or baseline compaction.
- `layout/engine` is a compatibility composition root, not a low-level domain
  dependency. It resolves the solver catalog and injects the selected strategy.
- `render`, `serve` and `cli` consume artifacts and stage APIs.

The native routing core imports no Python or solver logic. `bindings.rs` connects
it to the Python RouteGrid proxy. Both backends serve the same transaction API.

Import isolation is tested in `tests/test_framework.py`. See the
[framework manual](../framework/README.md) for extension contracts.
