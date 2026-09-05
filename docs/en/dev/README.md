---
title: Development
summary: Contributor-facing docs: the package map, the import order, the test suite, the viewer, and the assumptions still to verify.
tags:
  - dev
  - overview
---

# Development

For people working on the tool itself.

## Workflow

`CONTRIBUTING.md` at the repository root has the setup and the check commands; `CLAUDE.md` has the rules (Python 3.13, modern type hints, no imports inside functions, exact fractions for rates, registries over branching, comments that say what and never why). Read both before touching code.

## In this section

- [Internals](internals.md): the package map and the path of one run through the stages, with the files that carry each step.
- [Dependency graph](dependency-graph.md): the import order between packages and modules.
- [Testing](testing.md): the flat test suite, the benchmark scenarios, the engine tests, and the check commands.
- [Frontend](frontend.md): the web app's architecture, the run API, the event stream and the canvas renderers.
- [Assumptions](assumptions.md): game mechanics the tool assumes and has not verified in play, data gaps, and known limits.

## Solver benchmarks

- [Regional constructive baseline](regional-benchmarks.md): initial equal-time and
  equal-action results, reproduction commands, and known reliability limits.

## Code-near docs

Every subpackage under `src/kohakuefda/` has a `README.md` with a Files table and a Dependencies list. They are the most accurate description of what lives where; this section explains how the pieces fit.
