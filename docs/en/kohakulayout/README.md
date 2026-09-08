---
title: KohakuLayout
summary: A framework that turns a netlist into a layout on a grid; what it claims, what a project keeps, and where each part is documented.
tags:
  - kohakulayout
  - overview
---

# KohakuLayout

KohakuLayout (`src/kohakulayout/`) is a framework for one problem: a netlist of cells with
pins in, a placed and routed layout on a grid out. It knows nothing about any game or any
factory. A project states what the grid means through a *physics pack*, writes its problems
in a small text form, and runs the framework's solvers or its own through one engine.

The framework claims the part every layout tool re-solves and where silent failures live:
the intermediate representation and its two forms, the transactional world with its router,
budgets, rollback, assessment, checkpoints, the run lifecycle, and the conformance suite that
holds every pack and every solver to the same obligations. Planning (what to build) and
visualising (drawing the answer) stay with the project.

| page | what it covers |
|---|---|
| [The IR and its text form](ir.md) | the levels (netlist, problem, layout, assessment), modules and macros, the `.kl` language, JSON, digests |
| [Physics packs](physics.md) | how a project states its game: fabric, library, carriers, fields, boundaries, flow, rules, objective |
| [The world and the router](state.md) | placements, wires, units, reservations, transactions, the refusal chain, routing, the state checker |
| [The engine](engine.md) | context, builder, budget, attempts, the best archive, frames, plugins, checkpoints, workspaces |
| [Solvers](solvers.md) | the solver protocol, the shipped families, registries, level-3 conformance |
| [The service](service.md) | submit, watch, cancel, resume and result; run directories and the event log |
| [Utils and flow](utils-and-flow.md) | builders and passes over the netlist; the steady-state evaluator |
| [Conformance and gates](conformance.md) | the levels of proof, the check tiers, the ledger, the isolation test |
| [The native twin](../dev/kohakulayout-twin.md) | the Rust crate that reproduces the text form, digests and the kernel byte for byte |

## Vocabulary the framework never reads

Every cell, net, unit and finding carries a `kind` and an `attrs` dictionary keyed by the
pack's namespace. The framework passes them through and never interprets them; a pack's
hooks do. That is the line between mechanism (the framework's) and vocabulary (the project's).

## Where it lives

The framework and the Endfield project share one repository and one distribution for now.
`kohakulayout` imports nothing from `kohakuefda`; a subprocess test walks every framework
module to prove it. The design set, the round-by-round progress and the measurements live
under `.internal/kohakulayout/` and are not published.
