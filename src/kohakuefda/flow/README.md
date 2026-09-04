# flow/

The steady-state model: lane sizing against belt 30/min and pipe 120/min,
nets from producers to consumers with lane counts, the stability findings
(net-rate signs, sinks, fluid targets, activation, power, area), and the
evaluator that runs a placed layout to a fixed point.

## Files

| File           | Description                                                          |
| -------------- | -------------------------------------------------------------------- |
| `lanes.py`     | `lane_capacity`, `lanes_for`, `lane_split` (ports, rate per port, machines per lane), `machines_per_lane` |
| `nets.py`      | `build_nets`: proportional producer→consumer split, one `Net` each   |
| `stability.py` | `balance_findings`, `target_findings`, `resource_findings`           |
| `evaluate.py`  | `evaluate`: relaxation over segments and ports; sources (default rate or `config["rate"]`), sinks, dumps, gas zones, conduit pairs, activation, routers, bridges, control ports; crafters accept what they consume; per-segment rates and per-machine utilisation with the stalling cause |

## Dependencies

- `kohakuefda.model`, `kohakuefda.layout`
