---
title: Dependency graph
summary: The project's packages import one way, down to the model; the layout stage is a consumer of KohakuLayout, which never imports the project.
tags: [dev, internals, architecture]
---

# Dependency graph

Arrows mean imports; callbacks and injected implementations do not reverse them.

```text
cli / serve / scripts
       |
       v
layout stages / pipeline (composition; the layout stage runs KohakuLayout)
       |                  \
       v                   v
synth (problem, layout, frames)      kohakulayout (ir, physics, engine, pipeline, solvers)
       |                                     ^                      ^
       v                                     |                      |
physics (the Endfield pack) -----------------+    solvers (the project's own, on the protocol)
       |
       v
layout/board, chunk, geometry, connect, coverage, depot_via
       |
       v
verify / flow (the rule deck and the evaluator over a project layout)
       |
       v
     model
```

- `model` imports nothing of the project above it; `data` imports domain records only.
- `plan` and the flow arithmetic stay upstream of physical layout.
- `physics` is the Endfield pack: it imports `kohakulayout` (`ir`, `physics`) and nothing
  else of the project. It reads the `endfield` namespace of `attrs`; the framework never
  reads it.
- `solvers` is KohakuEFDA-kl's own construction and search on the framework's solver
  protocol; it imports `kohakulayout.solvers` and nothing else of the project, and the
  stage's name table is its only importer.
- `synth` turns the project netlist into a framework problem and a framework layout back
  into the project's placement and layout; it imports `model`, `layout/board`,
  `layout/fragments`, `layout/place` and the pack.
- `layout/stages` runs `kohakulayout.pipeline.solve` on the synth's problem;
  `layout/engine` maps the project's solver names and flat settings onto the framework's
  solvers; `layout/config` holds the settings and the studio's catalogue.
- `verify/rules` and `flow/evaluate` judge the project layout the synth emits; they use
  `route/grid` for occupancy and `layout/connect` for connectivity, never a solver.
- `render`, `serve` and `cli` consume artifacts and stage APIs.
- `kohakulayout` imports no `kohakuefda` module; `scripts/dev/kl_deps.py` and the
  isolation test enforce it, and the project imports only the framework's public modules.

See the [KohakuLayout pages](../kohakulayout/README.md) for the framework's own contracts.
