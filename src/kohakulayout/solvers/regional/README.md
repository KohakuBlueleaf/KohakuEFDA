# kohakulayout.solvers.regional

Seeded frontier construction with neighbourhood reconstruction of what is missing.

| file | what |
|---|---|
| `__init__.py` | `Regional` (id `regional`): the search, then shrink |
| `candidates.py` | `Proposals`: a clearance map with a gap, every fitting window by integral image, pack anchors for pinned cells, group windows, ranking by pin-to-target distance; `is_free` |
| `search.py` | `Search`: trials that restart or restore the best prefix and withdraw a region, insert by priority with pressure, refill, retain the best; `neighbours_of`, `clear` |
