# kohakulayout.solvers.structural

The second solver family: a floorplan over macros and free leaves, mutated, scored by a
surrogate, legalised through the same builder with channels as reservations.

| file | what |
|---|---|
| `__init__.py` | `Floorplan` (id `floorplan`): initial structure (or an exact packing), legalise, then mutate, screen by surrogate, legalise the promising ones |
| `representation.py` | the `Representation` protocol and `REPRESENTATIONS` registry; `Coordinate` (identity over anchors) |
| `floorplan.py` | `Rows`: items in rows with a channel under each row; `channels` become per-carrier reservations; `decode` places items and instances; `mutate` swaps, moves and flips |
| `surrogate.py` | `surrogate`: bounding area of the items plus a weighted half-perimeter wire estimate |
| `legalize.py` | `legalize`: one attempt that clears, reserves the channels, decodes and releases; the assessment when every cell lands |
| `exact/` | the exact slot: `protocol.py` (`Exact`, `EXACT`, `Infeasible`, absence is `NotAvailable`), `cpsat.py` (ortools), `milp.py` (highspy); each registers only when its library imports; ortools and highspy each bundle a HiGHS and the second to load fails to link, so `KOHAKULAYOUT_EXACT` (`cpsat` by default, or `milp`) names the one a process loads first |
