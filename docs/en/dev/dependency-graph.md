---
title: Dependency graph
summary: The project's packages import one way, down to the model; the layout stage places and routes through KohakuLayout, and the verify stage judges and evaluates through it, while the framework never imports the project.
tags: [dev, internals, architecture]
---

# Dependency graph

Arrows mean imports; callbacks and injected implementations do not reverse them.

```text
cli / serve / scripts
       |
       v
layout stages / pipeline (composition; the layout stage runs KohakuLayout)
       |                        \
       v                         v
verify (the checks and the evaluation over the synth's reverse translation)
       |
       v
synth (problem, reverse, layout, frames, modules)      kohakulayout (ir, physics, flow, verify, engine, pipeline, solvers)
       |                                                        ^                      ^
       v                                                        |                      |
physics (the Endfield pack) ------------------------------------+    solvers (the project's own, on the protocol)
       |
       v
layout/board, settings, router          plan (recipes, lp, planner, machines, netlist, depot)
       |                                        |
       v                                        v
flow (lanes, nets, stability, the evaluation schema)
       |
       v
     model (the domain records, footprints, the layout and placement schemas)
```

- `model` imports nothing of the project above it; `data` imports domain records only.
- `plan` and the flow arithmetic stay upstream of physical layout; `plan/depot` holds
  the depot access arithmetic and the fixed bus's slots the board reads.
- `physics` is the Endfield pack: it imports `kohakulayout` (`ir`, `physics`) and nothing
  else of the project. It reads the `endfield` namespace of `attrs`; the framework never
  reads it.
- `solvers` is KohakuEFDA-kl's own construction and search on the framework's solver
  protocol; it imports `kohakulayout.solvers` and nothing else of the project, and the
  stage's name table is its only importer.
- `synth` turns the project netlist into a framework problem, a framework layout back into
  the project's placement and layout, and a project layout from any source into a
  framework problem and layout (`reverse`); it imports `model`, `layout/board`,
  `plan/depot` and the pack.
- `verify` runs the framework's verify runner and its routed evaluator over the reverse
  translation, the rate rule over the evaluation against the plan, and holds the report.
- `layout/stages` runs `kohakulayout.pipeline.solve` on the synth's problem;
  `layout/settings` maps the project's solver names and flat settings onto the framework's
  solvers and holds the studio's catalogue; `layout/router` is the project's lane router.
- `render`, `serve` and `cli` consume artifacts and stage APIs.
- `kohakulayout` imports no `kohakuefda` module; `scripts/dev/kl_deps.py` and the
  isolation test enforce it, and the project imports only the framework's public modules.

See the [KohakuLayout pages](../kohakulayout/README.md) for the framework's own contracts.
