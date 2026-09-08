# kohakulayout.solvers.local

Hill climbing and annealing: one trajectory, two acceptance rules.

| file | what |
|---|---|
| `climb.py` | `LocalSolver` with `PARAMS` and validation; `HillClimb` (id `climb`) and `Anneal` (id `anneal`) |
| `anneal.py` | names `Anneal` for readers of the plan |
| `search.py` | `Trajectory`: construction by regional repair accepted on the gap delta, improvement by moves accepted on the area-first delta; the next move starts from current |
| `moves.py` | `ConstructionMoves` (regional and local repair regions), `LayoutMoves` (shift, rotate, swap, cluster, reroute, reroute_all, cut, pull, press, repack), the `MOVES` names |
| `compact.py` | `relocate`, `cut_candidates`, `press_candidates` (shared with the baseline shrink), `CompactionMoves` (cut, press, pull) |
| `repack.py` | `RepackMoves`: a neighbourhood, every other time rooted at the extent's edge, withdrawn and reconnected at ranked anchors inside one attempt |
| `policy.py` | `decide`, `temperature`, `layout_delta`, `gaps` |
| `frontier.py` | `Frontier.potential`: obstruction and endpoint distance for what is still missing |
