# kohakulayout.state

The live, transactional L2. Solvers mutate it through the engine's builder; the
world asks the physics for anchors, legality, sharing, cover and diagnosis and
interprets no kind and no attr.

| file | what |
|---|---|
| `world.py` | `World(problem, physics, kernel, router)`: place with the failure chain (legal, region, overlap, port_shut, field, route), rip and re-route, withdraw, route/unroute, place_unit, place_instance, reserve/release, transaction and marks, snapshot/restore, digest, freeze/load, queries |
| `chain.py` | the placement failure chain as functions over the world: `inspect` (legal, region, overlap with rip candidates, port_shut both ways), `cover` (the field stage through the cover planner) |
| `forms.py` | `freeze(world, hierarchical)` and `load(world, layout)`: the world as a Layout and back |
| `check.py` | `StateCheck`: the world's obligations as assertions (digest unchanged after a refusal, stage in the chain, holders match the record, reservations respected, restore identity) |
| `transaction.py` | `Transaction`: a journal of undo closures with marks; rollback on exit unless committed |
| `snapshot.py` | `Token`: a frozen copy of the record plus the kernel's bytes and the digest |
| `kernel/protocol.py` | the `Kernel` protocol (occupy, free, holders, free_for, cells_of, holders_on, extent, occupancy, integral, save, load, clear) and `holder_kind` |
| `kernel/python.py` | `PyKernel`: the reference occupancy grid, dict-based |
| `kernel/native.py` | `NativeKernel`: the Rust grid behind the same protocol; `make_kernel("auto")` picks it when built |
| `kernel/recording.py` | `RecordingKernel` logs every mutation as JSON lines around any kernel; `replay` drives another kernel with the log |
| `kernel/tables.py` | `ShareTable`: memoised `may_share` over occupant keys, the pairs a native kernel receives |
| `kernel/__init__.py` | `KERNELS` registry and `make_kernel` |
| `router/` | the router slot: protocol, path finder, trees, units, reservations, the default router (its own README) |

Holders are strings: `cell:<id>`, `wire:<net>`, `unit:<id>`, `reserve:<tag>`.

## Dependencies

`kohakulayout.errors`, `kohakulayout.ir`, `kohakulayout.physics`, numpy.
