---
title: The engine
summary: What a solver runs in: the context, the builder that is its only door to the world, budgets, attempts, the best archive, frames, plugins, checkpoints and workspaces.
tags:
  - kohakulayout
  - engine
---

# The engine

The engine gives a solver everything a search needs and owns nothing about how to search.

## Context

`Context(problem, physics, seed, kernel, router, checker, budget, plugins, progress, run,
execution)` builds the world and holds the seeded random generator that is the only
randomness a solver may use. `kernel` defaults to `auto`: the native twin when it is
built, else the Python kernel. Its surface:

| call | what it does |
|---|---|
| `builder()` | the door to the world |
| `attempt(fn, label, cost)` | runs `fn(builder)` inside a transaction; a returned or met refusal rolls it back and is recorded |
| `snapshot()` / `restore(token)` | the whole state as a token, and back |
| `assess()` | the assessment, through the screens and the dedup cache the plugins keep |
| `consider(token)` / `accept(token)` / `restore_best()` | the best archive: valid first, then complete, then the fewest gaps, then the objective's energy |
| `frame(phase, layout)` | a `Frame` through the sampler to the progress sink |
| `checkpoint()` / `resume(checkpoint)` | the world, the rng state, the budget spend and the best, as one JSON artifact |
| `scope(component, units)` | a phase name and an optional budget cap |
| `gather(tasks)` | the execution slot: in process, or a process pool |

## Builder

`place`, `place_instance`, `withdraw`, `route`, `unroute`, `reserve`, `release`, marks
inside a transaction, `anchors`, `admits` (the cheap half of `place`), `first_open`,
`diagnostic` (the last refusal) and `finish`. Every mutation charges one budget unit after
it ran, so a budget is never exceeded by more than one charge.

## Plugins

Cross-cutting policy is a plugin at a hook, never an engine feature. Hooks run linearly by
priority; `None` means unchanged, `DROP` discards a frame, `False` vetoes an assessment or an
accept. Built in: budget accounting (an attempt's opt-in cost), frame sampling by cadence,
metric screens before assessment (`area`, `missing`), assessment deduplication by digest,
repack cadence with a registry of repack actions, checkpoint cadence. `default_plugins()`
is budget, sampler and dedup.

## Workspaces and the pipeline

A `Workspace` is an oversized board with the target region in its middle; `overflow`
counts what lies outside, `project` translates a layout back onto the target and `publish`
hands it over only when nothing overflows. `pipeline.solve(problem, solver, seed, budget,
params, ...)` runs the passes (verification after each), then the solver on a context, and
returns the best layout, its assessment, the checkpoints and the events.
