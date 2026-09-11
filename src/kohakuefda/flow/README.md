# flow/

The steady-state model: lane sizing against belt 30/min and pipe 120/min,
nets from producers to consumers with lane counts, the stability findings
(net-rate signs, sinks, fluid targets, activation, power, area), and the
evaluation schema the verify stage fills from the framework's routed evaluator.

## Files

| File           | Description                                                          |
| -------------- | -------------------------------------------------------------------- |
| `lanes.py`     | `lane_capacity`, `lanes_for`, `lane_split` (ports, rate per port, machines per lane), `machines_per_lane` |
| `nets.py`      | `build_nets`: proportional producer→consumer split, one `Net` each   |
| `stability.py` | `balance_findings`, `target_findings`, `resource_findings`           |
| `evaluate.py`  | `Evaluation` (`segments`: `SegmentFlow` per segment and direct link with items, total and capacity; `machines`: `MachineState` with utilisation, inputs, outputs and the stalling cause; iterations, converged), `EPSILON` |

## Dependencies

- `kohakuefda.model`
