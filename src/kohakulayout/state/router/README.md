# kohakulayout.state.router

The router slot. The world calls `route(world, net)` inside the placing transaction;
the router writes wires and units through the world and refuses at stage `route`.

| file | what |
|---|---|
| `protocol.py` | `Router` protocol (`route`, `unroute`, `cost`), `Terminal`, `Costs`, `terminals(world, net)`, `refuse`, the registry (`register`, `make_router`, `ROUTERS`) |
| `reservations.py` | `walls(world, carrier)` from regions the pack closes; `reservation_price`: corridor for the own carrier, wall for any other |
| `pathfinder.py` | `Search` (one search's view), `entry` (the cost of a cell: free, shared, crossing, ripped or closed), `rules_of` (the search as tables for the native twin), `find` (A* from a cell set to a cell set with turn costs, bounded by `max_steps`; on a native kernel the twin's search answers first) |
| `trees.py` | `Plan`, `may_join` (where a junction unit can stand), `grow` (a tree: the sources join first into a trunk, then the sinks branch from the last join or from one another, nearest-first within each phase; junctions by the terminal reached) |
| `units.py` | crossing units, junction units and repeaters (cut so no run exceeds the limit, never on a segment's end cell) placed through `world.place_unit`; a field emitter in a unit's way is removed (`emitter_at`) and every placed cell left short is covered again (`recover`) |
| `default.py` | `DefaultRouter(ripup, **costs)`: negotiated congestion with rip-up and history, commits a plan, re-routes what it displaced |

## Dependencies

`kohakulayout.errors`, `kohakulayout.ir`, `kohakulayout.physics`, `kohakulayout.state.kernel`.
