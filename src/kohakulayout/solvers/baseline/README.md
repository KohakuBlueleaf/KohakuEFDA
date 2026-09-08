# kohakulayout.solvers.baseline

Construct a complete routed spread, then compact it greedily.

| file | what |
|---|---|
| `__init__.py` | `Baseline` (id `baseline`): spread, or parallel spread slices when the context has workers and no unit budget, then shrink |
| `spread.py` | `Spread`: seeded flow-order traversal, a lattice of squares with a gap that widens per retry, rotations facing placed partners, pack anchors for pinned cells, group windows |
| `shrink.py` | `Shrink`: carve an empty line, press toward each side, nudge toward partners; every relocation is one attempt kept only when the assessment ranks better |
| `parallel.py` | `build_parallel`: seeded slices through the execution slot; `construct_slice` is the picklable task |
