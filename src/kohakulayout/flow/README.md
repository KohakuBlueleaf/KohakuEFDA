# kohakulayout.flow

The steady-state evaluator: what every pin receives and every source makes, under the
pack's `Flow` hooks (split, merge, demand, transfer), with findings.

| file | what |
|---|---|
| `evaluate.py` | `evaluate(netlist, flow, fabric, evaluator)` and the `EVALUATORS` registry (the slot) |
| `fixedpoint.py` | `FixedPoint`: the greatest fixed point under the declared rates, downward only, loops primed; `cycles`; `Evaluation` |
| `findings.py` | `kl.flow.starved`, `kl.flow.capacity`, `kl.flow.loop`, `kl.flow.unstable` |

## Dependencies

`kohakulayout.errors`, `kohakulayout.ir`.
