# kohakulayout.templates

The framework's own instances and skeletons. Each ships with its test; a template without
a test is a trap.

| directory | what it is |
|---|---|
| `physics/null/` | every default and a tiny library; `problem(width, height, taps)` builds the null instance, an instrument |
| `physics/gates/` | the first instance: gates on a grid; `problem(netlist, **params)`, `from_expressions`, `random_circuit` |
| `solver/` | `skeleton.py`: the copyable minimal solver, construct through anchors and attempts, one improvement idea |
| `plugin/` | `identity.py`: every hook returning None, counting its calls |

Importing `kohakulayout.templates` registers the packs with `kohakulayout.physics`.
