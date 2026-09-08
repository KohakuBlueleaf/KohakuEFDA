# kohakulayout.utils

Functions over the IR a project may call from its synth or its adapters. Framework code,
tested with the framework, on no framework path: the engine never calls one. Imports
`ir` and `errors` only.

| file | what |
|---|---|
| `build.py` | `cell`, `add_cells`, `add_footprint`, `add_net`, `next_id`, `pin_for`; `chain`, `fanout`, `bank`, `hub`, `entries`, `instantiate` |
| `passes/lanes.py` | `lanes(nl, fabric)`: nets over their carrier's capacity split into lane nets, first-fit over equal sink shares |
| `passes/replicate.py` | `replicate(nl, max_fanout, buffer_footprint, buffer_kind)`: buffers in a tree so no net exceeds the fan-out |
| `passes/surplus.py` | `surplus(nl, sink_footprint, sink_kind, demand)`: a sink cell on every net over its demand |
| `passes/balance.py` | `balance(nl, demand, fabric)`: findings `kl.balance.unfed`, `starved`, `surplus`, `capacity` |
| `passes/macros.py` | `macros(nl, strategy, gap)`: the `MACROS` strategies `bank`, `group`, `custom`; `form` makes one module, one macro with a row fragment and its derived footprint, and one instance |
