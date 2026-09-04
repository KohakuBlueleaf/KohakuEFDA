---
title: Verification
summary: The geometry rules that reject a layout the way the game would, and the steady-state evaluator that proves it runs at the plan's rates.
tags:
  - concepts
  - verify
  - overview
---

# Verification

Every layout, whether generated, imported or hand-made, is judged by the same two instruments:

1. [Geometry rules](geometry-rules.md): each rule, what it catches, and why the game would refuse the layout otherwise.
2. [Steady state](steady-state.md): what the evaluator models, how it converges, and how the rate rule compares its result to the plan.

The report that collects their findings is the artifact a layout is judged by: a layout with no error passes. `kohakuefda check` runs both on any layout file; `kohakuefda layout` runs them on its own output.
