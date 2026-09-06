# local/

Matched hill-climbing (`hc`) and simulated-annealing (`sa`) heuristic baselines.
Both construct without a spread seed and then search complete routed layouts.
They share move generation and differ only in uphill acceptance.

## Files

| File | Provides |
|---|---|
| `__init__.py` | Validated shared defaults, HillClimbing and SimulatedAnnealing |
| `moves.py` | Regional refill and complete-layout mutation proposals |
| `compact.py` | Compound gap compression and connection-directed relocation proposals |
| `repack.py` | Scoped whole-region reconstruction action with bounded coupled insertion |
| `policy.py` | Area-first bounded tie-break, acceptance, work-based cooling and physical identity |
| `search.py` | Current-state construction and improvement trajectories, best archives and transition events |

## Behavior

Construction energy counts missing machines. Regional insertion/region helpers
serve both methods without the regional best-prefix search loop.

Complete-state energy is `(area + w * L / (B + L)) / B`, where `L` is
actual routed wire-path length, `B` is board area and `w=wire_tiebreak` is in
`[0, 1)`. The length term cannot outweigh a single cell of area. HC accepts
improvement and nonidentical neutral candidates; SA additionally samples positive
deltas with `exp(-delta/T)`. Both reject identical physical realizations.

With `compaction_moves=true`, the shared move mixture includes compound one-cell
compression across machine-free lines and relocation toward connected machines.
Each has twice the sampling weight of an original move. Compression moves only
the changed blocks and reroutes affected connections through a normal transaction;
unrelated routing is preserved. Candidates are deduplicated within the current
snapshot and refreshed after accepted route or placement changes. Pull proposals
include legal alternate depot slots and fluid entry positions. Their anchor score
is a proposal heuristic, never the acceptance metric.

Every `repack_every=16` improvement proposals, a spatial region of up to
`repack_size=8` ungrouped machines is removed and reconstructed inside one scoped
action transaction. Refill considers up to `repack_candidates=24` anchors per
machine with `repack_gap=1`. Every removed machine and affected route must be
restored before the candidate may be considered. The ordinary HC/SA policy decides
acceptance; repack has no separate greedy acceptance rule. Set `repack_every=0`
to disable it. Temporary action registration is released on all solver exits.

The next move starts from current, not best. Construction may retain an assessed
partial state after a whole withdrawal/refill transaction; only missing-machine
findings are exempted from its gate. Accepted complete states must always pass
full geometry and routing checks. Failed, cancelled and budget-interrupted trials
roll back without undoing work accounting. Rates never affect acceptance.

SA cools geometrically using charged actions plus route calls within each phase.
Construction temperatures use missing-machine units; layout temperatures use
fractions of board area. This cooling counter is reproducible, not a claim that
all actions or route calls cost equal compute. Setting both temperatures of a
phase to zero gives HC acceptance. Proposal and acceptance RNGs are independent.
Construction retains `cooling_work=100000`; improvement uses
`layout_cooling_work=20000` and cools from `0.02` to `0.0000001` by default.

`DEFAULTS` exposes all local policy controls. Regional operator geometry defaults
come from `solvers.regional.DEFAULTS`; there is no adaptive selector, restart,
population, auto-temperature calibration or greedy-shrink pass. Runs are serial.
`until_budget=true` continues each enabled phase until the supplied global
`seconds` or `max_actions` budget ends, ignoring nonzero step caps. Without a
global budget, or with `until_budget=false`, the configured finite step caps
apply. Zero still disables a phase: `improvement_steps=0` stops at first complete
construction. Empty proposals charge an action so action-limited runs terminate.
A supplied routed snapshot skips construction, enabling matched improvement-only
tests. More budget extends the search, not a guarantee of further improvement.
Cooling is based on work already spent, not the eventual stop budget.

`transition` events include parent, candidate, next parent, best, energy delta,
temperature, draw, outcome, actual area/wire deltas and work. Studio frames honor world `frame_every`
(zero disables them). `best_routed` is the best factory, not necessarily current
at an annealing stop. No exact search-resume claim is made by layout checkpoints.

## Dependencies

- `kohakuefda.framework`, `kohakuefda.model`.
- Regional proposal/repair helpers, not its search or greedy compaction policy.
- External: `numpy` through regional candidate generation.
