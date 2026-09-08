# kohakulayout.state.router

The router slot. The world calls `route(world, net)` inside the placing transaction;
the router writes wires and units through the world and refuses at stage `route`.

| file | what |
|---|---|
| `protocol.py` | `Router` protocol (`route`, `unroute`, `cost`), `Terminal`, `Costs`, `terminals(world, net)`, `refuse`, the registry (`register`, `make_router`, `ROUTERS`) |
| `reservations.py` | `walls(world, carrier)` from regions the pack closes; `reservation_price`: corridor for the own carrier, wall for any other |
| `pathfinder.py` | `Search` (one search's view), `entry` (the cost of a cell: free, shared, crossing, ripped or closed), `find` (A* from a cell set to a cell set with turn costs, bounded by `max_steps`) |
| `trees.py` | `grow`: nearest-terminal growth from the first source to every terminal and the net's edge; junctions per the pack's rule; a `Plan` |
| `units.py` | crossing units, junction units and repeaters placed through `world.place_unit` |
| `default.py` | `DefaultRouter(ripup, **costs)`: negotiated congestion with rip-up and history, commits a plan, re-routes what it displaced |

## Dependencies

`kohakulayout.errors`, `kohakulayout.ir`, `kohakulayout.physics`, `kohakulayout.state.kernel`.
