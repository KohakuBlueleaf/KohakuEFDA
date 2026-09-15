# solvers/

KohakuEFDA-kl's own solvers: the project's construction and search algorithms written
against KohakuLayout's solver protocol. They import the framework and nothing imports
them but the stage's name table. The framework's `regional`, `climb` and `anneal` stay
its own examples; these carry the project's rules and are what `regional`, `hc` and `sa`
run.

## Files

| File | Description |
|---|---|
| `__init__.py` | Registers the three solvers on import; `SOLVER_IDS` |
| `regional.py` | `EndfieldProposals` (the clearance map of placed footprints with their gap and nothing else, so a window may cross a lane the footprint displaces; the first cells pulled to a third of the Core AIC Area, the rest and every depot part after the first to its corner; a depot part with no placed mate on a lattice in the origin corner (`depot_window`, `depot_step`); every fitting window, no attach clearance; a lane's targets are the cells the lane router would open on the partner pin's own lanes (`lane_ends`: the lane policy's origins over the lanes it feeds or the lanes into it, read back from the wire's segments), else every attach cell the placed partner pin may still use), `EndfieldSearch` (its jitter from the raw seed over the cells in their declared order; cells no net touches first, then cells with a placed neighbour (a pair once per lane), where neighbours are the two ends of a lane from the pack's lane facts, not every cell on a net; no bounding-box term, one routed lookahead), `EndfieldRegional` (id `endfield.regional`; an insertion gives up after `INSERT_FAILURES` (16) refused anchors, where the old engine scanned every candidate, so a repair step costs a fraction and the same work places more; `NET_FAILURES` (0, off) would end it after that many route refusals on one net, measured neutral at equal work); the lane targets come one per lane, so a pin with several lanes is scored once per lane |
| `local.py` | `EndfieldClimb` (id `endfield.climb`) and `EndfieldAnneal` (id `endfield.anneal`): the framework's local searches constructing and repairing with `EndfieldSearch` |

## Dependencies

- `kohakulayout.solvers` (`Regional`, `HillClimb`, `Anneal`, `register`, the regional
  `Search` and `Proposals` they subclass, `Param`).
- `kohakuefda.physics.facts` (`lane_facts`: the pack's lane vocabulary in a net's attrs).
- Nothing else from the project: the solvers see the world through the framework.
