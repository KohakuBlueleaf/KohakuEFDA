---
title: Framework API reference
summary: Solver contracts, immutable records, actions, settings, events and failure semantics.
tags: [framework, reference, api]
---

# Framework API reference

## Entry points

`framework.problem_of(dataset, netlist, plan=None) -> Problem` captures exact
serialized domain inputs with a content digest. Later mutations to caller-owned
models do not affect the problem. Rates remain fraction strings in serialization.

`framework.solve(problem, solver, *, seed=None, strict=True, **options)` builds a
`framework.runtime.Runner` and executes it. Options are `settings`, `world`,
`actions`, `routing`, `coverage`, `objective`, `observe`, `cancelled`.
`Runner.context` exposes the same operations for an interactive Python caller.
Do not use `Runner.backend.site` in a solver: it is an adapter implementation.

## Runtime settings

| Setting | Default | Meaning |
|---|---|---|
| `seed` | 0 | Strategy seed; namespace RNGs are available from Context |
| `workers` | 1 | Baseline construction concurrency; 0 auto-selects up to 16 cores |
| `max_actions` | 0 | Maximum builder placement/withdrawal attempts plus improvement attempts; 0 unlimited |
| `seconds` | 0.0 | Cooperative elapsed-time limit; 0 unlimited |
| `backend` | `auto` | `auto`, `python`, `native`; explicitly requesting unavailable native fails |
| `check_rates` | true | Assess final current rates when a plan is supplied |

Negative budgets, non-finite numbers and unknown keys are rejected. Boolean
settings require booleans. These settings are separate from strategy settings.
The legacy layout stage omits `check_rates`: its Verify stage performs that job.

World settings are in `framework.config.WORLD_DEFAULTS`: pylon, entry sides,
routing penalties and diagnostic weights. `frame_every` remains a compatibility
setting; construction frames currently report every placed machine. `w_*` terms
in `Site.cost()` are diagnostic; they do not replace `AreaWire` ordering.

## Baseline settings

`Baseline(**settings)` accepts: `spread_attempts=32000`, `spread_slice=64`,
`spread_gap=0`, `spread_widest=6`, `shrink_rounds=200`, `flow_order="bottom-up"`.

The first complete geometry-checked spread wins. Shrink tries carve, press and
nudge through the common transaction gate and takes the first strict area/wire
improvement. With workers, baseline owns deterministic slice/seed scheduling and
selects the first successful result in seed order from a completed batch. The
actual worker snapshot is imported; construction is not replayed for animation.
All completed worker work is accounted, including discarded contenders.

Custom routing/coverage instances or a deterministic action cap select the serial
baseline path, so these do not silently vanish in child processes. Batch jobs
are opt-in services; other solvers need not follow baseline's batch policy.

## Regional settings

`Regional(**settings)` constructs without a spread seed. It places and routes
one machine at a time, retains best partial checkpoints, and withdraws spatial
neighborhoods of missing machines for reconstruction. After `finish()` succeeds,
optional greedy shrink operates only on complete routed states.

Core defaults: `attempts=128`, `candidates=150`, `gap=2`, `gap_cycle=2`,
`refill_rounds=1`, `restart_cycle=4`, `repair_threshold=0.85`, `radius=7`,
`radius_cycle=14`, `neighbor_cycle=3`, `expand_cycle=5`, `shrink_rounds=200`.
All scoring and pressure defaults are exposed in `solvers.regional.DEFAULTS`
and `/api/solvers`. Regional execution is serial; select `regional` in Studio
and use `solver_options` JSON for overrides. A time limit can end compaction
with a valid best result: inspect `best_routed`, not just the stop status.

Regional preserves the input netlist and the backend's logical connections.
Its acceptance criteria are complete placement, legal routing, and passing geometry
checks. Rate evaluation is optional and separate from layout acceptance.

## HC and SA settings

`HillClimbing` and `SimulatedAnnealing` in `solvers.local` are catalog entries
`hc` and `sa`. Both are serial, share coupled moves, and continue from their
current state rather than restoring best before each proposal. They do not run
the baseline's greedy shrink. HC accepts lower or equal energy; SA also samples
positive deltas with `exp(-delta/T)`. Identical physical states are rejected.

Construction uses missing-machine count and assessed withdrawal/refill transactions.
`insertion_lookahead=6` compares extra routed anchors after the first successful
insertion, selecting shortest actual routes. Zero restores first-fit insertion.
Experimental `frontier_weight=0` may be set up to0.5 to add a bounded optimistic
footprint-obstruction and endpoint-distance score for missing machines. It is not
proof of connectability. `local_repair_every=0` disables small repairs; N>=2 chooses
local trials on N-1 steps followed by one regional trial, with
`local_repair_size=3` as the maximum local scope. These are typed construction
controls in Studio. Defaults leave the experimental score and local trials off.

Area and occupied bounding rectangles include only cells inside the build area.
External pipe cells remain in routing state, verification and total route length;
they do not inflate occupied width/height/area.

Complete-layout energy is `(A + w * L / (B + L)) / B`, using actual
area `A`, wire-path length `L`, board area `B` and `0 <= wire_tiebreak = w < 1`.
The length term only breaks area ties: it cannot outweigh a single area cell.
Shift, rotate, swap, connected-group shift, reroute, gap compression, and
connection-directed relocation proposals share the same acceptance gate.
Every accepted complete state passes the framework gate. `best_routed` remains independently
ordered by the configured objective; it can differ from the current SA state.

Shared defaults: `construction_steps=128`, `improvement_steps=2000`,
`candidates=150`, `gap=2`, `repair_actions=12000`, `repair_route_calls=24000`,
`move_radius=4`, `cluster_size=3`, `compaction_moves=true`, `compact_choices=6`,
`pull_radius=6`, `wire_tiebreak=0.5`, `cooling_work=100000`,
`layout_cooling_work=20000`, `until_budget=true`, `repack_every=16`,
`repack_size=8`, `repack_candidates=24`, `repack_gap=1`.
Each compaction move has twice the sampling weight
of an original move. Gap compression transactionally relocates only changed
blocks; pull moves sample short-connection candidates, including legal depot
slots and border entries. Every `repack_every` proposals, the solver instead
reconstructs a sampled spatial region inside one scoped action transaction. All
removed machines and affected routes must be reconnected before normal HC/SA
acceptance applies. `repack_every=0` disables this move. Failed repairs roll back
and retain their charged actions and route calls. All routes still require full validation.

SA temperatures: construction `2.0` to `0.05` (missing-machine units), layout
`0.02` to `0.0000001` (board-area fractions). Cooling is geometric by charged actions
plus route calls since the phase began, clamped at the final temperature.
The construction and layout phases use their respective work horizons. This
work sum is a deterministic cooling clock, not an equal-compute measurement.
Both temperatures of a phase can be zero for HC-equivalent acceptance.

With the default `until_budget=true` and a supplied global time/action budget,
enabled phases run until that budget ends rather than stopping at a nonzero step
cap. With no global budget, or `until_budget=false`, step caps still apply. A zero
step count always disables its phase: `improvement_steps=0` stops at first complete
construction. Empty proposals consume an action to avoid infinite no-work loops.
Budget-driven frames have `of=0` because their step total is not predetermined.
A supplied routed snapshot starts improvement immediately. Proposal and acceptance RNG streams are
separate. `transition` events record parent, candidate, next parent, best, delta,
temperature, probability, draw, result, actual area/wire deltas and work; frames
use `frame_every`. Disable `compaction_moves`, set `repack_every=0`, and set
`wire_tiebreak=0` to use the original move set and area-only energy.
The best archive never worsens, but continued search can still plateau.
No adaptive operator selection, restart, or exact search-history resume is implied.

## State records (`model.solver`)

| Record | Contents |
|---|---|
| `Problem` | ID, dataset/netlist/optional plan JSON, rules identity |
| `BlockInfo` / `Lane` / `PortChoice` | Immutable geometry and compatible local endpoint domains |
| `ConnectionTarget` | Link ID, local lane ID, immutable opposite-end port/tree cells |
| `WorldView` | Revision, board, anchors, footprint tuples, occupied cells, missing/ready-unrouted sets |
| `Snapshot` | Problem ID, state ID, backend payload, exact layout and placement JSON, Assessment |
| `Assessment` | Completeness, geometry/routing/rates verdicts, issues, metrics |
| `Candidate` | Issuing session, base revision and checked snapshot |
| `Scope` | Permitted machine IDs, permitted route IDs or None, support-change permission |
| `Action` | Name, anchor edits, rebuild order, route IDs, optional scope/options |
| `AttemptResult` | Status, optional candidate, message and required-route expansion |
| `SolveEvent` | Sequence, kind, elapsed/duration, revision, immutable payload JSON |
| `SolveResult` | Stop status, current/diagnostic, best routed/verified, elapsed/work/settings/error |

`Assessment.routed` requires complete geometry-checked routing. `verified` also
requires a passing rate result. Verdicts are `pass`, `fail`, `not_checked`.
No input plan means rates are not checked. A completed run can return no verified
snapshot; callers must not substitute a proxy score for this evidence.

## Context operations

| Operation | Contract |
|---|---|
| `view`, `blocks`, `links` | Read-only physical queries; no solver-owned aliases into Site |
| `slot_anchors`, `border_anchors`, `group_anchors` | Legal-domain candidate queries |
| `connection_targets(block_id)` | Opposite-end cells for connections to placed blocks; no physical-state mutation |
| `rng(namespace)` | Persistent per-namespace deterministic Random instance |
| `builder()` | Construct only while no complete current exists |
| `attempt(action, base_revision=None, *, screen=None)` | Execute in scratch; optional metric-only rejection before checks; always restore base |
| `accept(candidate)` | Validate issuing context/revision and atomically publish |
| `discard(candidate)` | Release the pending candidate's in-memory backend mark |
| `consider(snapshot)` | Offer current or an issued candidate snapshot to best archives without moving current |
| `import_snapshot(snapshot)` | Check digest/problem/settings, reconstruct and reassess; rollback invalid imports |
| `verify()` | Recompute current rates; returns a new evidence-bearing snapshot |
| `emit(kind, payload, duration)` | Emit solver diagnostics via the common read-only event envelope |
| `frame(kind, **fields)` | Emit legacy-compatible construction/improvement frame |
| `gather(function, jobs)` | Isolated batch execution, results in input order; solver owns selection |

Current is read-only to the solver. Archives compare offered snapshots using the
objective. Pending candidates consume memory until accepted/discarded or the
context is released. Importing a snapshot changes revision; old candidates cannot
be committed over it. Runtime errors propagate with `strict=True` after rollback;
`strict=False` returns `error` with the last published result.

## Construction withdrawal

`builder.withdraw(tuple_of_block_ids)` removes those blocks and reroutes affected
connections whose endpoints remain placed. It charges one action and returns
`removed` only when all remaining ready routes exist. Failure, exception,
cancellation or budget exhaustion restores the exact previous prefix. This is
construction-only; it cannot remove machines from a published current state.
Use `mark/restore/release` to retain a prefix while exploring a refill.

`builder.finish()` emits `constructed` after geometry-checked publication;
observers can record time to first routed state at this boundary.

## Compound construction trials and local allowances

`with builder.transaction() as trial:` groups multiple builder operations.
`trial.assess()` materializes the candidate and checks placed geometry, support,
groups and ready routes; only missing-machine findings are permitted. Its returned
snapshot may be partial and is not published. `trial.accept()` retains that
assessed revision at normal context exit. Without acceptance, or after any
exception/cancellation/deadline, the pre-trial physical state is restored even
though normal builder methods would refuse work after the deadline. Work remains
charged. Nested/reused trials and stale acceptance are rejected. `finish()` is
allowed only after the trial closes and still requires complete routed geometry.

`with budget.limit(actions=n, route_calls=m):` temporarily bounds named counters.
Nested allowances all apply; zero allows no additional work of that kind.
`LocalBudgetExhausted` distinguishes a failed bounded repair from a global budget
or cancellation stop. It is a `BudgetExhausted` subclass, so solvers continuing
after local repair failure must catch it before the global exception. Allowances
never reset global counters; the global action/deadline checks take precedence.

## Builtin actions

- `Action("relocate", anchors=((id, (x, y, rotation)), ...))`: remove named
  machines, then place/route them in the supplied order. Supports compound edits,
  but sequential group checks may reject a jointly feasible rearrangement.
- `Action("rebuild", anchors=..., order=...)`: remove/rebuild all placements.
  Its scope must include every removed block, even ones returning to the same spot.
- `Action("reroute", routes=(wire_id, ...))`: rip those wires and dependent
  attachments, release port claims and reconnect through the chosen router.

Custom handlers implement `(Workspace, Action) -> None`. Workspace supports
`view`, `put`, `remove`, `reroute`, `check`. They operate only in authorized
scope; expired workspaces refuse further operations. Support may be recomputed
unless `scope.support=False`. Scope rejects unauthorized resulting route changes
and reports required IDs; it does not guarantee the repair algorithm is complete.

Ordinary outcomes: `candidate`, `not_found`, `hard_conflict`, `scope_required`,
`unsupported`, `stale`, `screened`. Builder adds `placed` and `removed`. Budget/cancellation exceptions stop
the enclosing runtime as `budget_exhausted`/`cancelled`; neither publishes scratch.
An action's failure means no replacement found under the attempted choices,
not a global impossibility proof.

## Measurement and acceptance

`AreaWire.key(assessment)` returns `(area, wire_path_cells)`.
`area` is the pylon-inclusive occupied bounding box inside the basement;
`occupied_cells` is the union count; `waste` is their difference.
`length` counts emitted segment cells; `wire_path_cells` counts backend wire paths
and can count shared cells repeatedly. They intentionally have different names.
Width/height, pylons, junctions and underused bricks are also reported.

An injected objective needs `name` and `key(assessment)`. It orders candidates,
never decides legality. A solver may use a different private acceptance energy
or accept a larger valid layout, while retaining the best objective result.

### Optional metric screening

`screen` is a callable receiving an immutable mapping of actual materialized
metrics, including pylons and emitted routing. Returning false produces `screened`
with no candidate or feasibility claim. Returning true only permits the usual
full validation and serialization; it cannot authorize an unchecked candidate.
Exceptions and cancellation in the screen restore the base through the same
transaction boundary. Screens must be pure and must not re-enter the Context.

Baseline uses `AreaWire.key_metrics(metrics)` to screen non-improvements before
checking the whole layout. Objectives without that optional method retain the
full candidate path. This is not an anchor-distance estimate or a routability
prediction: routes already exist when measured.

Within one revision, baseline also skips repeated rebuild anchor arrangements.
Different empty cut lines can produce the same arrangement. This pruning is
restricted to the builtin deterministic actions, routing and coverage; custom
implementations are not assumed repeatable. A new accepted state clears the
cache. `duplicate_rebuilds` is recorded separately from executed `actions`.

### Profiling the baseline

Run `python scripts/dev/profile_shrink.py --output out/shrink-profile/current`
from the repository root. Construction is outside the shrink timer. Use
`--run-dir out/runs/16828e4d` for original saved inputs, `--profile` for cProfile,
and `--no-screen --no-deduplicate` for the reference behavior. Profiling overhead
is substantial: compare unprofiled repetitions for elapsed-time claims. Reports
include per-round counts and the accepted-state sequence for differential checks.

## Time, cancellation and persistence

Events separate total run elapsed time from individual attempt/worker duration.
Worker times overlap and must not be summed as wall time. A deterministic work
budget is reproducible for a fixed seed/backend/settings; a timed stop depends
on machine load. Observer errors are logged without altering the solution.

Cancellation is cooperative between edits/routing calls; a running native A*
call is not interrupted internally. Isolated batch children are terminated and
joined on cancellation/error. Python callers must supply a cooperative callback
or time budget; this is not a security sandbox for untrusted extensions.

Snapshot checkpoint schema 1 saves concrete routing, not arbitrary solver-private
state. Load through `framework.checkpoint`, then import through Context. Exact
search resume and topology-changing source/sink assignment are not implemented.
