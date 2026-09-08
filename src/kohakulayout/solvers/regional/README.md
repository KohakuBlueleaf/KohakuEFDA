# kohakulayout.solvers.regional

Seeded frontier construction with neighbourhood reconstruction of what is missing.

| file | what |
|---|---|
| `__init__.py` | `Regional` (id `regional`): the search, then shrink |
| `candidates.py` | `Proposals`: a clearance map with a gap that also marks wire cells and attach cells (`ring` adds their neighbours), every fitting window by integral image with the attach cells clear, pack anchors for pinned cells, group windows, ranking by pin-to-target distance, bounding-box growth (`extent_weight`) and a pull to the origin corner; `is_free` |
| `search.py` | `Search`: trials that restart or restore the best prefix and withdraw a region, insert by priority with pressure through a routed lookahead (`lookahead` placed anchors compared by wire cells, `insert_failures` refusals end the scan), refill, retain the best; `neighbours_of`, `clear` |
