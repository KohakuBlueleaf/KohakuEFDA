# kohakulayout.solvers.local

Hill climbing and annealing: one trajectory, two acceptance rules.

| file | what |
|---|---|
| `climb.py` | `LocalSolver` with `PARAMS` and validation, and the construction `search` a project's solver replaces; `HillClimb` (id `climb`) and `Anneal` (id `anneal`); `complete` |
| `search.py` | `Trajectory`: construction by the regional repair of the given `search` (one non-strict attempt, so what placed is kept) accepted on the gap delta, improvement by moves accepted on the area-first delta; every improvement proposal is reported to the moves' `feedback` |
| `moves.py` | `ConstructionMoves` (regional and local repair regions through the given search), `LayoutMoves` (shift, rotate, swap, cluster, reroute, reroute_all, cut, pull, press, repack with the search's `proposer`, reseat of the search's `reseated` constraint kinds every `reseat_every`; `batch_moves` settles every footprint before routing; `adaptive_moves` draws the ordinary operators through `OperatorSelection`), the `MOVES` names |
| `compact.py` | `relocate`, `cut_candidates`, `press_candidates` (shared with the baseline shrink), `CompactionMoves` (cut, press, pull) |
| `repack.py` | `RepackMoves`: a neighbourhood, every other time rooted at the extent's edge, withdrawn and reconnected at ranked anchors inside one attempt |
| `policy.py` | `decide`, `temperature`, `layout_delta`, `gaps` |
| `frontier.py` | `Frontier.potential`: obstruction and endpoint distance for what is still missing |
| `selection.py` | `OperatorSelection` (seeded exploration, recent reward per square root of charged work) and `reward` |

## Dependencies

- `engine`, `ir`, `state` and `physics` through the solver context.
- `solvers.regional` for repair proposals, neighbourhoods and the reseated kinds.
