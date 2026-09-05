---
title: Regional constructive baseline
summary: Initial routed-layout results, limitations, and reproducible comparisons against spread and shrink.
tags: [dev, benchmarks, solvers]
---

# Regional constructive baseline

`regional` is a randomized greedy constructor with regional ruin-and-recreate
and optional greedy compaction. It is **not** simulated annealing, a genetic
algorithm, or the final exploratory search design. It keeps a single best partial
checkpoint and does not retain worse candidates as a continuing search trajectory.
Its useful contribution is a stronger constructor and a reusable repair mechanism.

## Physical contract

The solver consumes the existing plan/netlist, preserving logical connections.
Every placed prefix routes its ready connections. A partial checkpoint is only a
construction diagnostic. Published layouts must be complete, routed, and
geometry-checked. Compaction uses the same complete-state gate as the baseline.
Balancing belongs to planning/netlist construction; starvation findings are not
layout acceptance criteria or established evidence that routing caused a shortfall.

## Initial measurements

Dataset `1.5.3@9764758-3`; seeds 0, 1, 2; native backend; one worker; default solver
settings. Five test-owned `scenario_dense_*.toml` inputs specify absolute targets,
gas disabled, zero wood, and enumerated natural supplies. Expanded areas are
70×70 for Valley and 80×80 for Wuling (REG-04).

Each study includes both solvers on all five cases and three seeds. A success is
a complete geometry-checked routed snapshot, even when subsequent compaction
stops at the budget. Rates were intentionally not evaluated in these studies.

| Case | Baseline: 60 s | Regional: 60 s | Baseline: 100k actions | Regional: 100k actions |
|---|---:|---:|---:|---:|
| Valley6 | 3/3 | 3/3 | 3/3 | 3/3 |
| Valley12 | 0/3 | 1/3 | 0/3 | 2/3 |
| Valley18 | 0/3 | 0/3 | 0/3 | 0/3 |
| Wuling6 | 0/3 | 1/3 | 0/3 | 2/3 |
| Wuling12 | 0/3 | 0/3 | 0/3 | 0/3 |

For the 60-second study:

| Case / solver | First routed seconds, seeds 0/1/2 | Best actual area, seeds 0/1/2 |
|---|---|---|
| Valley6 baseline | 0.056 / 0.058 / 0.069 | 2976 / 2976 / 2976 |
| Valley6 regional | 2.548 / 2.069 / 2.216 | 2655 / 1989 / 1989 |
| Valley12 regional | 46.205 / — / — | 4620 / — / — |
| Wuling6 regional | 18.182 / — / — | 5846 / — / — |

Regional's successful Valley12 footprint is 70×66 and Wuling6 is 74×79.
For Valley6 it uses 10.8–33.2% less area and finishes construction plus compaction
1.39–2.19× sooner. **Baseline is faster to the first Valley6 solution.** A dash
means no complete result within budget, not an omitted slow success.

At 100k actions, regional also completes seed 2 for Valley12 (first at 84.262 s,
area 4830) and Wuling6 (first at 61.613 s, area 5760). This is not an equal-time
speedup: an action rejected on footprint fit is much cheaper than a routed
regional reconstruction. Routing-call counts and elapsed times differ greatly.
Three seeds per case are preliminary observations, not robust reliability claims.

## Provenance and reproduction

Original local evidence directories are `out/dense-equal-time-v1/` and
`out/dense-equal-work-v1/`; they are ignored development artifacts, not shipped
with this repository. This page preserves their summary. Each contains a manifest,
per-case plan/netlist/scenario, per-run results, events, and first/best/diagnostic
snapshots where available. They were measured on an uncommitted development tree
based on `ec45a1e`, not on a clean release. A refill control-flow correction was
applied between the studies; the published implementation includes it. Do not
interpret the studies as bit-identical algorithm revisions or promise exact times.

Run from the repository root with fresh output directories:

```sh
PYTHONHASHSEED=0 python scripts/dev/benchmark_dense.py \
  --solvers baseline,regional --seeds 0,1,2 --seconds 60 \
  --max-actions 0 --no-verify-rates --output out/dense-time-new

PYTHONHASHSEED=0 python scripts/dev/benchmark_dense.py \
  --solvers baseline,regional --seeds 0,1,2 --seconds 0 \
  --max-actions 100000 --no-verify-rates --output out/dense-work-new
```

The default case list includes all five required scenarios. Run serially without
competing benchmarks. Use `--verify-rates` only for separate post-search evaluator
diagnostics; that does not measure time to a verified state during search. The
`constructed` event records the publication boundary for first routed results.

## Remaining work

Improve dense construction reliability, continue exploration after the first
complete state, and handle Valley18/Wuling12 without depending on a spread seed.
Keep this solver as an independently selectable baseline. More jitter, a larger
candidate budget, or a new method name alone is not evidence of better exploration.
