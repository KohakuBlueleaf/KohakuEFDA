# kohakulayout.solvers.regional

Seeded frontier construction with neighbourhood reconstruction of what is missing.

| file | what |
|---|---|
| `__init__.py` | `Regional` (id `regional`): the search, then shrink; a project's solver subclasses it with its own `search` |
| `candidates.py` | `Proposals`: a clearance map with a gap that also marks wire cells and the reserved attach cells, every fitting window by integral image (an array of anchor rows) with the cell's own first attach cells clear (`attach_clear`, a method a subclass may relax), pack anchors for pinned cells, group windows, ranking by the distance from any port a pin may use to its targets, by bounding-box growth (`extent_weight`) and by the `pull` (the first cells to the build box's origin corner, `origin_weight`, the rest by `corner_weight`; a subclass may pull elsewhere); `is_free`; `targets` names each own pin once per placed partner pin; port offsets kept per cell and rotation; a constrained cell's anchors from `World.anchor_rows` |
| `contact.py` | `ContactProposals`: every fitting anchor scored by a distinct-port assignment of the cell's pins to their targets per carrier, bounding-box growth, the `pull` and alignment with same-sized footprints, then kept spatially diverse (`candidate_bucket`, `bucket_quota`) |
| `assignment.py` | `distinct_cost`: the cheapest injective pin-to-port assignment per candidate anchor (exact up to `MAX_PORTS` ports, per-pin minima past it) |
| `search.py` | `Search`: trials that restart or restore the best prefix and withdraw a region, insert by priority with pressure (pinned cells first, then cells with a placed neighbour) through a routed lookahead (`lookahead` placed anchors compared by wire cells; `insert_failures` refusals end the scan, as do `net_failures` route refusals naming one net), refill, retain the best by placed cells; `defaults`, `proposer`, `neighbourhood`, `priority` and `reseated` are what a project's construction overrides; `neighbours_of`, `clear` |

## Dependencies

- `kohakulayout.ir`, `kohakulayout.physics.protocol`, `kohakulayout.solvers.base` and `baseline.shrink`.
- The application supplies lane targets through `targets`; nothing here reads a pack's vocabulary.
