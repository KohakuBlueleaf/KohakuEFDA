# tests/kohakulayout

The framework's suite, tiered by shape. Run through `python scripts/dev/kl_check.py`.

| directory | shape |
|---|---|
| `test_isolation.py` | the central claim: the framework imports no project, in a subprocess |
| `unit/` | one source file, one test file; behaviour asserts, real collaborators |
| `integration/` | one framework package, one class whose methods are complete workflows |
| `journey/` | end-to-end runs through the service; marker `journey` |
| `parity/` | Python against the Rust twin, skipped when the native module is absent |
| `bench/` | `bench_*.py` scripts printing `metric <name> <value>` for the ledger |
| `fixtures/` | `.kl` files as triplets: `name.kl`, `name.flat.kl`, `name.json` |
