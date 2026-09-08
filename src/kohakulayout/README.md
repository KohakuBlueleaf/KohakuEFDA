# kohakulayout

The framework: a netlist in, a layout out. The design set is `.internal/kohakulayout/`
in this repository; this README describes what exists.

## Import order

One way, measured by `scripts/dev/kl_deps.py` and the isolation test:

```
errors -> ir -> utils (imports ir only)
              -> physics -> state -> flow -> verify -> engine -> solvers -> pipeline -> service
templates may import anything below them; cli is the top.
```

`kohakulayout` imports nothing from `kohakuefda` or any other project.

## Files

| file | what it is |
|---|---|
| `errors.py` | typed exceptions; imports nothing |
| `_rust.py` | `HAS_RUST` and the guarded import of `kohakulayout_rs` |
| `_rust_bridge.py` | one wrapper per accelerated function; `None` means fall back to Python |

## Subpackages

| package | purpose |
|---|---|
| `ir/` | the levels: netlist, problem, layout, assessment, refusal, frame; JSON and text forms |
| `utils/` | builders and passes over the IR; on no framework path |
| `physics/` | the physics protocol and its defaults |
| `state/` | the world, transactions, kernels, the router |
| `flow/` | the steady-state evaluator |
| `verify/` | the rule runner and the structural rules |
| `engine/` | context, builder, budget, assessment, progress, checkpoints, plugins |
| `solvers/` | the solver protocol, registries and the shipped solvers |
| `pipeline/` | passes and the problem-to-layout function |
| `service/` | the run lifecycle and the event envelope |
| `templates/` | the null and gates packs, the skeleton solver, the identity plugin |
| `cli/` | the `kl` dev commands |
