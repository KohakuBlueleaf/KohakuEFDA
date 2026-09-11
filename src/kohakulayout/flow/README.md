# kohakulayout.flow

The steady-state evaluators: what every pin receives and every source makes under the
pack's `Flow` hooks, over the netlist or over a layout's wires, with findings.

| file | what |
|---|---|
| `evaluate.py` | `evaluate(netlist, flow, fabric, evaluator, layout)` and the `EVALUATORS` registry (the slot); `layout` goes to the evaluators that read one |
| `fixedpoint.py` | `FixedPoint` (`fixedpoint`): the greatest fixed point under the declared rates over the netlist, downward only, loops primed; `cycles`; `Evaluation` (per pin and per net, plus `runs` and `cells` when the evaluator fills them) |
| `routed.py` | `Routed` (`routed`): a layout's wires as nodes (pins at their attach cells, units, a crossing unit one node per way of travel, branch cells, segment boundaries, dangling ends) and runs between them along each segment, in the segment's order when `oriented` and else turned toward the sink pins, plus the pack's off-grid `links`; each round the cells accept and produce (`accept`, `produce`), the units admit (`merge_accept`), filter (`passes`) and share (`share`) commodity by commodity (`commodity`), and every run carries what it accepts under its carrier's capacity; stops when nothing moves, when the flows rounded to `snap` hold, or under `epsilon`; `RunFlow` and `CellFlow` in the evaluation |
| `findings.py` | `kl.flow.starved`, `kl.flow.capacity`, `kl.flow.loop`, `kl.flow.unstable` |

## Dependencies

`kohakulayout.errors`, `kohakulayout.ir`.
