---
title: The service
summary: How a solve is started, watched, stopped, saved and resumed; the run directory every run keeps and the one event envelope everything observable travels in.
tags:
  - kohakulayout
  - service
---

# The service

`SolveService` is one protocol with two implementations: `LocalService` runs the engine in
the caller's process and `ProcessService` spawns a worker per run. A project calls the
protocol and never learns which it got.

| call | what it does |
|---|---|
| `submit(problem, request) -> run id` | starts a run; `Request` names the solver, its params, the seed, the budget, the router and the checkpoint cadence |
| `status(run)` | state (`queued`, `running`, `done`, `incomplete`, `failed`, `cancelled`), phase, budget used, best metrics |
| `events(run, filter)` | the event log, filtered by kind and sampled |
| `cancel(run)` | a flag the run sees at its next attempt, in any process |
| `result(run)` | outcome, best layout, assessment, checkpoints |
| `best(run)` | the live best layout |
| `resume(checkpoint, request)` | a new run continuing from a checkpoint, recording its parent |
| `wait(run, timeout)` | joins the worker and polls the directory until the run is final |

A request that cannot start, such as an unknown solver, is a `failed` run carrying its
error, never an exception out of `submit`. A missing worker process or an optional part
that is not installed is `NotAvailable`, a configuration answer, never a failed solve.

## The run directory

```
runs/<run_id>/
  problem.json          the problem, so the run is reproducible from the directory alone
  request.json          solver, params, seed, budget, and the physics class path
  status.json           rewritten on every accept and checkpoint
  best.layout.json      the best layout so far
  best.assessment.json
  checkpoints/<seq>.json
  events.jsonl          one event per line: status, frame, assessment, refusal, checkpoint, log
```

Everything is a self-describing IR artifact, so a project's persistence layer can index
runs without the framework. `kl solve --root <dir>` records a run through the local
service; `kl runs <dir>` lists them.
