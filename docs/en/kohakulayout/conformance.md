---
title: Conformance and gates
summary: The levels of proof a pack and a solver climb, the tiered check script, the benchmark ledger, and the isolation test behind the framework's central claim.
tags:
  - kohakulayout
  - testing
---

# Conformance and gates

"Does my pack work" and "does my solver work" are each two questions: is the game right,
and is the thing a legal client of the framework. The levels keep them apart and the cheap
ones come first.

| level | what it proves |
|---|---|
| 0 | the framework's own suite on a clean tree, the gates pack included |
| 1 | pack data: footprints, carriers and rules as you meant them |
| 2 | state conformance: the state checker mounted on a world built from your pack and driven by the in-order solver |
| 3 | solver conformance: budget, frames, reproducibility, resume, the toys completed |
| 4 | end to end: your scenario to a layout and an assessment, graded on the answer |
| 5 | the benchmark ledger against its baseline |

## The check script

```
python scripts/dev/kl_check.py fast      # black, ruff, comment budget, the dependency lint, isolation, unit tests
python scripts/dev/kl_check.py unit      # fast plus the integration tests
python scripts/dev/kl_check.py journey   # unit plus the service journeys
python scripts/dev/kl_check.py bench     # the native module present, cargo fmt and clippy, the parity suite, the ledger
```

Every check is bounded; one that produces no result inside its budget is reported as
STALLED, a different event from FAIL. The ledger (`scripts/dev/kl_ledger.py`) records what
every bench under `tests/kohakulayout/bench/` printed; a later run fails when a recorded
count moved and reports when a timing moved beyond its tolerance.

## The isolation test and the dependency lint

`tests/kohakulayout/test_isolation.py` imports every framework module in a subprocess and
fails if any project module was pulled in. `scripts/dev/kl_deps.py` fails an import against
the one-way order (`errors` to `ir` to `utils` to `physics` to `state` to `flow` to `verify`
to `engine` to `solvers` to `pipeline` to `service` to `templates` to `cli`), a cycle, an
in-function import without an allow-listed reason, or any `kohakuefda` import.
