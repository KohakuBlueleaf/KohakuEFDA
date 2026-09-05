# route/

The two-layer occupancy grid (0 ground, 1 sky), the A* pathfinder with legal
crossings and soft congestion, and the router that turns nets into wires,
trees, trunks, bridges, repeaters and segments. RouteGrid selects native/Python
per instance and snapshots both mirrors, history and wire identities. Router
accepts an optional cooperative check callback from the execution framework.

## Files

| File            | Description                                                   |
| --------------- | ------------------------------------------------------------- |
| `grid.py`       | `Occupancy` (claims, conflicts, lookups; outside inputs claim the sky of their cell) and `occupancy_of` |
| `pathfinder.py` | `RouteGrid` (wire holders per layer with an axis at every cell, history, unit cells, reservations, turn/bridge/history costs), `astar` (bounding-box heuristic; a reserved cell may be crossed perpendicular to its owner's straight path) |
| `router.py`     | `Wire` (with `role` and `item_id`), `assign` (best-fit source ← sink pairing on positions), `wires_of` (pipe nets with several sources and sinks as merge-then-split trunks), `grid_of` (a grid blocked by a layout and, for belts, its ring), `Router` (farthest-sink-first trees that may branch in front of a port; trunk joins and branches with bounded rip-and-retry; negotiated congestion with present cost, growth and pass limit; rip-up cascades to dependants; strict or reporting mode with `unrouted`; branch splitters, join convergers, bridges, repeaters; segments carrying `heading`, `entry` and `item_id`; `wire` and `pass` frames; cancellation), `route_layout` |

## Dependencies

- `kohakuefda.model`, `kohakuefda.layout`
- External: `numpy`
