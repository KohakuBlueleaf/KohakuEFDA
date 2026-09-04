# verify/

Rules with an id, a severity and a locatable subject, run over layouts
(geometry and rate rules) and, through `flow/stability.py`, over plans. The
report is the machine artifact; the CLI renders it.

## Files

| File                | Description                                                                 |
| ------------------- | --------------------------------------------------------------------------- |
| `report.py`         | `Report`: findings, verdict, save/load                                      |
| `rules/geometry.py` | bounds, overlap, segment shape and run length, port connections and merges, unit counts, conduit links, gas zones, pylon coverage (12×12 squares from the dataset's pylons), the core, the area and its ring, depot bricks touching a Depot Bus with their back face, a laid bus one cluster with its port, outside inputs on the border, pipe over machine; `check_layout` |
| `rules/rates.py`    | `rate_findings` over an evaluation: convergence, crafters below utilisation 1, idle sources |

## Rule ids

`geom.bounds`, `geom.overlap`, `geom.segment_empty`, `geom.segment_gap`,
`geom.segment_loop`, `geom.run_length`, `geom.dangling_start`,
`geom.dangling_end`, `geom.port_shared`, `geom.merge`,
`geom.fluid_router_count`, `geom.conduit_missing`, `geom.conduit_kind`,
`geom.conduit_distance`, `geom.zone_overlap`, `geom.zone_missing`,
`geom.power` (warning: no pylon at all), `geom.power_uncovered`,
`geom.core_missing` (warning), `geom.core_count`, `geom.outside_area`,
`geom.belt_in_ring`, `geom.depot_bus` (warning when no bus is placed, error
when a brick's back face touches no bus part; a Valley IV bus is located
through the layout's area), `geom.bus_connected`, `geom.entry_off_border`,
`geom.entry_shared`, `geom.pipe_over_machine`, `flow.unconverged`,
`flow.starved`, `flow.idle` (warning). The layout stage adds
`layout.square_unknown`, `layout.too_big`, `layout.group_faults`,
`layout.unrouted`, `layout.uncovered`.

## Dependencies

- `kohakuefda.model`, `kohakuefda.layout`, `kohakuefda.route`, `kohakuefda.flow`
