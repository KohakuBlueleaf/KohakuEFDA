---
title: Writing a layout solver
summary: Run the baseline, implement an independent strategy or action, and reuse checked snapshots.
tags: [framework, tutorial, solvers]
---

# Writing a layout solver

## Run the baseline

Run from the repository root. The ordinary CLI and Studio use this same solver.
For parallel construction, put library entry-point code behind a `__main__` guard.

```python
from pathlib import Path

from kohakuefda.framework import problem_of, solve
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.scenario import Scenario
from kohakuefda.plan.netlist import build_netlist
from kohakuefda.plan.planner import plan
from kohakuefda.solvers.baseline import Baseline


def main():
    dataset = Dataset.load(Path("data/1.5.3@9764758-3/dataset.json"))
    scenario = Scenario.from_toml(Path("tests/fixtures/scenario_valley_battery.toml"))
    planned = plan(dataset, scenario)
    netlist = build_netlist(dataset, scenario, planned)
    problem = problem_of(dataset, netlist, planned)
    result = solve(problem, Baseline(), settings={"seed": 0, "workers": 1})
    if result.best_verified is not None:
        Path("out").mkdir(exist_ok=True)
        Path("out/framework-layout.json").write_text(result.best_verified.layout_json)
    return problem, result


if __name__ == "__main__":
    main()
```

Passing a plan enables rate verification. `completed` means the strategy stopped
normally; inspect `best_verified`, `best_routed`, and the issues rather than
interpreting the stop reason as production success.

## Run regional construction

For dense plans, replace `Baseline()` with `Regional()` from
`kohakuefda.solvers.regional` and use runtime settings such as
`{"seed": 0, "seconds": 60, "backend": "native", "check_rates": False}`.
Read `result.best_routed` for the physical-layout result. Use
`Regional(shrink_rounds=0)` to stop at the first complete construction.
No spread seed is required; construction and repair both keep ready routes legal.

In Studio choose `regional` and set a time budget. Policy overrides go in the
`solver_options` JSON field, for example `{"attempts": 256, "shrink_rounds": 0}`.
Balancing belongs to planning; rate evaluation is optional diagnostics rather
than a regional acceptance penalty.

## Run hill climbing or simulated annealing

Select `hc` or `sa` in Studio. Both use the same coupled move operators and
maintain separate current and best states. HC accepts improvements and neutral
moves; SA can also accept worse legal states. The baseline remains the default.

In Python, use `HillClimbing` or `SimulatedAnnealing` from
`kohakuefda.solvers.local` with the same `problem` built above:

```python
from kohakuefda.framework import solve
from kohakuefda.solvers.local import SimulatedAnnealing

result = solve(
    problem,
    SimulatedAnnealing(improvement_steps=2000),
    settings={"seed": 0, "seconds": 60, "backend": "native", "check_rates": False},
)
layout = result.best_routed
```

Check for `None` before using the layout. Use `improvement_steps=0` for
construction only, or pass a routed `seed` to compare improvement on an existing
layout. At an SA stop, current may be larger than best; use `best_routed` to
retrieve the best retained geometry. Studio exposes time/action budgets, backend,
seed and policy stop controls at the top of the layout inspector. The advanced
sections provide typed controls for every remaining selected-solver setting;
`solver_options` remains a synchronized optional JSON editor, for example
`{"layout_temperature": 0.01}`. Baseline-only spread/workers controls are hidden
for HC/SA. The time preset buttons set seconds, remove the action cap and enable
budget-driven search; they do not enable phases whose step count is zero.

A solver stop without a routed result is labelled **incomplete**, not an execution
failure or a proof that the board is too small. The outcome panel reports the stop
reason, placement count, work and last-run resolved settings. When a complete
routed result exists, budget exhaustion retains it and the stage is **done**.
Verification does not run automatically after an incomplete layout.

HC/SA default to `until_budget=true`: with a supplied time or action budget they
continue searching beyond nonzero construction/improvement step caps. Increase
`seconds` to allow more work. Best output never worsens, though some runs plateau.
To enforce a finite step cap instead, set
`{"until_budget": false, "improvement_steps": 4000}`. With no global budget the
finite step caps always apply. `improvement_steps=0` still skips improvement.
Regional repacking is enabled every 16 improvement proposals; set
`{"repack_every": 0}` to disable that move without changing HC/SA acceptance.

## Write a strategy

A strategy needs `name`, `capabilities` and `solve(context) -> str`. It can be a
plain class; no inheritance and no central optimizer branch are required.
This example needs an existing routed seed and tries rerouting once:

```python
from kohakuefda.framework import Action


class RewireOnce:
    name = "rewire-once-v1"
    capabilities = frozenset({"reroute"})

    def solve(self, ctx):
        routes = tuple(link.id for link in ctx.links)
        trial = ctx.attempt(Action("reroute", routes=routes))
        if trial.candidate is not None:
            candidate = trial.candidate
            if ctx.objective.key(candidate.snapshot.assessment) < ctx.objective.key(ctx.current.assessment):
                ctx.accept(candidate)
            else:
                ctx.discard(candidate)
        return "completed"
```

Use `solve(problem, RewireOnce(), seed=result.best_routed)` with the same problem
and world settings. The framework reconstructs and re-assesses the seed before
calling the strategy. Its saved evidence is not trusted on import.

`attempt()` leaves current unchanged. A candidate is an immutable snapshot plus
a session/revision token. Accept it only after deciding to continue from it;
discard unused candidates to release their in-memory routing snapshots. A solver
may accept a larger routed state. The best archive remains monotonic under the
run's configured objective.

## Construct without a seed

Use `ctx.builder()` to get a construction context. `place(id, (x, y, rotation))`
places and routes ready connections together and returns `placed` or a failed
attempt status. `reset()` clears a construction attempt. `mark/restore/release`
manage in-session partial checkpoints. `finish()` requires all machines and
routes plus passing geometry before publishing current. The baseline's
`solvers/baseline/spread.py` is a complete example using only these public calls
and immutable queries.

`builder.withdraw((id, ...))` atomically removes a construction region and repairs
remaining ready connections. Restore a saved mark when a refill does not help.
`ctx.connection_targets(id)` exposes read-only opposite port/tree cells for
scoring proposals. Neither operation changes logical source–sink allocation.
The regional solver is a second example using only the public framework surface.

A BuildState is not an improvement incumbent. Once current exists, a new builder
cannot clear it; use transactional actions or a separate run.

## Add a primitive without changing the kernel

```python
from kohakuefda.framework import Action


def move_pair(workspace, action):
    for block_id, _ in action.anchors:
        workspace.remove(block_id)
    for block_id, anchor in action.anchors:
        workspace.put(block_id, anchor)

```

Pass `actions={"move_pair": move_pair}` to `solve()` or `Runner()`. The strategy
then calls `ctx.attempt(Action("move_pair", anchors=...))`.

Workspace offers `view`, `put`, `remove`, `reroute` and `check`. It is closed after
the attempt; retaining it does not permit later edits. Every handler shares the
same rollback, completeness, scope and geometry gate. Raise `Rejected` for an
ordinary failed edit; other exceptions propagate by default after rollback.
`strict=False` converts solver exceptions to an error result for application use.

Default scope permits listed machine edits and rerouting affected connections.
Use `Scope(machines, routes, support=False)` to also constrain route changes and
freeze support placement. Dependency changes outside that scope return
`scope_required`; the framework never silently accepts the expanded edit.

## Hierarchical scope

`framework.scopes.component(ctx, members)` returns the machine-footprint union
and the internal/boundary links. Its `scope()` creates an explicit route/machine
permission set. This is a view, not an opaque rectangle, a reserved region, or an
optimizer that chooses groups. The solver owns partitioning and rearrangement.

## Checkpoint and restart

```python
from pathlib import Path
from kohakuefda.framework.checkpoint import load_snapshot, save_snapshot

save_snapshot(result.best_routed, Path("out/seed.json"))
seed = load_snapshot(Path("out/seed.json"))
```

This saves exact routed state, not arbitrary private solver state or the next RNG
position. Reuse it as `seed=` in another solve. It is restart-from-layout, not
exact continuation of a paused search.

## Register an application-visible solver

The application composition root owns the catalog:

```python
from kohakuefda.framework import Entry
from kohakuefda.solvers import SOLVERS

SOLVERS.register(Entry("my_solver", MySolver, {"rounds": 10}, "My strategy"))
```

Registration happens in trusted Python at application startup. `/api/solvers`
exposes names, versions, defaults and descriptions. The stage selects `solver`
and accepts a JSON object string in `solver_options` for custom settings. Library
callers can instead inject objects directly. HTTP cannot import arbitrary code.

## Test your extension

`tests/test_framework.py` demonstrates an independent solver and custom handlers
using real routing. Cover: candidate discard, failed relocation, out-of-scope
changes, exception/cancellation rollback, a second action after rollback,
checkpoint import and repeatability. A valid route result is not proof that a
particular flow topology meets the production plan; inspect the rate report too.
