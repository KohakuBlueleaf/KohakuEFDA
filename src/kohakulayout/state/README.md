# kohakulayout.state

The live, transactional L2. Solvers mutate it through the engine's builder; the
world asks the physics for anchors, legality, sharing, cover and diagnosis and
interprets no kind and no attr.

| file | what |
|---|---|
| `world.py` | `World(problem, physics, kernel, router)`: place with the failure chain (legal, region, overlap, port_shut, route, field; a router with `route_all` lays the nets a placement touches together, else they route one by one in the router's order; `trim` keeps a lane bundle's other lanes when a footprint takes one, a head or tail at its own port cell hanging only through a junction unit), rip and re-route, withdraw, place_unit, place_instance, reserve/release, transaction and marks, snapshot/restore, digest, freeze/load, queries; a field's coverage is kept until an emitter comes or goes, `units_rev` counts every unit change (undo included) for the caches that read the units, the nets a placement touches route in the router's `order` (the widest span first without one),; `admits` and `place` ask the twin first (`native_admits`, `native_attempt`); `anchor_rows`, the boundaries' anchors as rows |
| `wiring.py` | `WiringMixin`, the wire side of the world: `route` (through the router, rolled back on refusal), `set_wire`, `unroute` (the wire, its units and every other net's unit that stood only because of it), `trim` (only the segments a footprint cuts and what hangs from them: a lane that leaves from or joins into a taken lane's own cells, judged by laying order and, at a port cell, by the lane laid first; the rest a routed wire the router grows again), `runs_of` (the sides a wire continues to on each of its cells, written into the kernel with the wire), `forget_routes` |
| `attach.py` | `AttachMixin`: every port a placed pin may use with its attach and port cells (`port_choices`, memoised per placement), the port in use (`choice`: the wire's, else the first; `routed_port` names none for a pin with a choice its wire has not reached; a bound pin's only attach cell stays reserved as open while its wire does not hold it), the ports a pin may still take (`open_ports`), the nets a cell touches (`ready`: a placed source and sink; `grown_nets`: routed nets a new pin joins), and `Tables`: per layer the reserved attach cells of unrouted single-port pins, the attach and port cells routed wires use, and every alternative; patched per cell when a placement comes or goes (`table_cell`, `untable_cell`) and per net when a wire does, kept consistent through the world's undo log; `nets_of` reads a table built once from the flat netlist, `options_at` the port offsets kept per footprint and rotation |
| `chain.py` | the placement failure chain as functions over the world: `inspect` (legal, region, overlap, port_shut both ways; what a footprint may displace comes back as the nets to rip and the emitters to place again, `displaceable`), `cover` (the field stage through the cover planner) and `recover` (cover again what the removed emitters it is given reached, one coverage per field); a unit on an attach cell connects the pin only when it belongs to the pin's own net, and another net's wire on it leaves the pin open only where the pin's wire may cross it (`crossing.crossable`); a field emitter on it leaves the pin open, the route displaces it |
| `crossing.py` | where one wire may cross another on a cell: `straight_through` (the other wire's run on the cell continues to both sides across and to neither side along, read from the kernel's runs, its port behind an attach cell counted), `unit_allowed` (the pack lets a unit stand in every region holding the cell; `region_cells` once per fabric), `occluded_free` (a crossing unit's other layers free), `crossable` (the pack's rule allows it, the other wire runs straight through along some axis, and a crossing unit, when needed, may stand there and has the cell to itself); asked by the placement chain for attach cells and by the path finder for every cell and for a path's own ends |
| `forms.py` | `freeze(world, hierarchical)` and `load(world, layout)`: the world as a Layout and back |
| `check.py` | `StateCheck`: the world's obligations as assertions (digest unchanged after a refusal, stage in the chain, holders match the record, reservations respected, restore identity); two wires on one cell only under a unit or where the pack lets them share (`sharing`) |
| `transaction.py` | `Transaction`: a journal of undo closures with marks; rollback on exit unless committed |
| `snapshot.py` | `Token`: a frozen copy of the record plus the kernel's bytes and the digest |
| `kernel/protocol.py` | the `Kernel` protocol (occupy, free, set_runs and run_at for the sides a wire holder continues to on a cell as bits N=1 E=2 S=4 W=8, holders, free_for, cells_of, holders_on, extent, occupancy, integral, save, load, clear) and `holder_kind` |
| `kernel/python.py` | `PyKernel`: the reference occupancy grid, dict-based |
| `kernel/native.py` | `NativeKernel`: the Rust grid behind the same protocol; `make_kernel("auto")` picks it when built |
| `kernel/recording.py` | `RecordingKernel` logs every mutation as JSON lines around any kernel; `replay` drives another kernel with the log |
| `kernel/tables.py` | `ShareTable`: memoised `may_share` over occupant keys, the pairs a native kernel receives |
| `kernel/__init__.py` | `KERNELS` registry and `make_kernel` |
| `router/` | the router slot: protocol, path finder, trees, units, reservations, the default router (its own README) |

Holders are strings: `cell:<id>`, `wire:<net>`, `unit:<id>`, `reserve:<tag>`.

## Dependencies

`kohakulayout.errors`, `kohakulayout.ir`, `kohakulayout.physics`, numpy.
