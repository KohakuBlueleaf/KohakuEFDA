---
title: Solver framework
summary: Build Endfield layout strategies without reimplementing the physical model, transactions or application runtime.
tags: [framework, solvers, development]
---

# Solver framework

The framework provides immutable problem/snapshot records, read-only physical
queries, transactional placement/routing actions, geometry and rate assessment,
budgets, isolated worker execution, checkpoints and events. The baseline is a
client of this API, not a search loop built into the framework.

```text
CLI / Studio / embedding
          |
          v
   runtime.Runner              config, cancellation, timing, results
          |
          v
   Solver.solve(Context)      strategy owns proposals and acceptance
          |
          v
   Context / Builder          checked transactions and safe publication
          |
          v
   SiteBackend                world, routes, support, snapshots
          |
     +----+-------------------+
     |                        |
 Python grid             Rust grid / A*
     +-----------+------------+
                 |
          shared assessment
```

## Ownership

| Category | Provided by the framework | Solver author owns |
|---|---|---|
| Fixed contract | Required machines/flows, actual routing, scope, rollback, evidence | Obey it; do not replace legality with penalties |
| Replaceable mechanism | Action handlers, Site routing/coverage implementations, objective | Inject a compatible implementation |
| Convention | Seed from the baseline, greedy/local actions | Use another constructor or search structure |
| Strategy | Context queries and operations | Traversal, destinations, regions, acceptance, restarts, private history |

The problem is a fixed production plan. Lowering delivery or changing recipes is
not a legal placement action. Belt port defaults are preferences: alternatives
retain the full compatible domain regardless of ingredient processing order
(JCT-08). Pipe alternatives retain the dataset's recipe binding domains (JCT-09).

## Start here

- [Manual](manual.md): run the baseline, write a solver and action, save/reuse a seed.
- [API reference](reference.md): exact records, operations, settings and outcomes.
- [Backend boundary](backends.md): Python/Rust ownership and extension limitations.

## Source organization

```text
src/kohakuefda/
  model/solver.py            immutable problem, snapshot, action, event records
  framework/                mechanisms; imports no concrete solver
  solvers/baseline/          first-feasible spread + greedy shrink policy
  layout/engine.py           stage composition/compatibility adapter
  layout/site.py             mutable physical substrate (backend-owned)
  route/                    Python routing and optional native proxy
  verify/ flow/              shared rule checks and rate evaluation

src/kohakuefda-rs/
  lib.rs                    module registration and backend API version
  bindings.rs               PyO3 boundary and grid snapshot checks
  route/core.rs             solver-independent occupancy and A* kernels
  route/tests.rs            native routing tests
```

Importing `kohakuefda.framework` does not import `kohakuefda.solvers`. This is
checked in a fresh subprocess by the framework tests. Application adapters own
catalog registration and strategy selection.

## Scope of this implementation

Working: construction; single/compound relocation and full reconstruction;
explicit rerouting; geometric scope checks; portable routed seeds; separate
routed/verified best records; custom action/solver injection; parallel baseline
construction; library, CLI and Studio integration.

Not claimed: a complete repair router, a competitive new heuristic, exact resume
of arbitrary solver-private state, automatic source/sink reassignment, arbitrary
pipe recipe/configuration switching, or a full component-library optimizer.
Components are query/scope views, not a global hierarchical optimization policy.
A bounded routing failure means not found, not proof of impossibility.

The existing rate evaluator is retained. A snapshot can be completely routed yet
fail rate verification; the framework exposes both facts. No plan supplied means
rates are `not_checked`, never an implicit pass.
