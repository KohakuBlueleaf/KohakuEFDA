# kohakulayout.solvers

A solver is a strategy over a context. It never sees a cell kind, a rule or a pack's name.

| file | what |
|---|---|
| `protocol.py` | `Param`, `Outcome` (`complete`, `incomplete`, `failed`) and the `Solver` protocol |
| `params.py` | `resolve(declared, given)`: typed coercion, defaults, unknown names refused |
| `base.py` | `BaseSolver`: `run` is the loop (start frame, construct, constructed frame, consider, improve, `BudgetExhausted` → incomplete, restore the best, end frame); `construct` and `improve` are yours |
| `conformance.py` | `level3(solver_id, toys)`: completes, valid best, frames, budget charged and never exceeded by more than one charge, seed reproduces layout and events, resume from a checkpoint |
| `registry.py` | solvers by id: `register`, `get`, `known` |
| `inorder.py` | `InOrder`: cells in flow order, each at the first anchor that takes it; the null solver |
| `anchors.py` | the anchor generator registry `ANCHORS`: every, facing, frontier, group |
| `baseline/`, `regional/`, `local/` | the coordinate-level family: baseline, regional, climb, anneal (each its own README) |
| `structural/` | the structural family: `floorplan` over representations, the surrogate, legalisation, the exact slot (its own README) |

## Dependencies

`kohakulayout.errors`, `kohakulayout.ir`, `kohakulayout.engine` (through the context a caller passes).
