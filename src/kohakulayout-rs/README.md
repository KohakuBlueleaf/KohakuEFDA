# kohakulayout-rs

The native twin of KohakuLayout. Python is the ground truth; every function here reproduces
a Python function byte for byte and is held to it by `tests/kohakulayout/parity/`.

| path | what |
|---|---|
| `src/ir/model.rs` | every level as serde types with the same defaults pydantic dumps |
| `src/ir/rate.rs` | rates as normalised fractions, crossing JSON the way `str(Fraction)` writes them |
| `src/ir/json.rs`, `digest.rs` | canonical JSON (sorted keys, no whitespace, unicode kept) and its sha256 |
| `src/ir/geometry.rs`, `hier.rs`, `flatten.rs` | rotations, attach cells, rectangle covers; pins and footprints; the macro footprint; `flatten` |
| `src/text/kl.pest` | the grammar, mirroring `ir/text/kl.lark` rule for rule |
| `src/text/parser.rs`, `assemble.rs`, `writer.rs` | text to statements to levels, and levels to canonical text |
| `src/text/levels.rs` | the JSON boundary: parse, write, flatten, canonical, digest |
| `src/kernel/grid.rs` | the occupancy grid with `PyKernel`'s exact `save()` bytes, the runs of every wire holder per cell included; per-slot maps with an index of each holder's cells |
| `src/kernel/hash.rs` | the kernel's maps and sets (`Map`, `Set`) on a word-at-a-time multiplicative hasher; no answer depends on their iteration order |
| `src/kernel/astar.rs` | the path search over the grid, the found path and the classified layer it takes, with the net's own crossable lane cells (`own`) and the sources' order passed per search, f32 cost sums when the rules set `float_scale`, no end on a crossing when they say so; one record per state and per cell in buffers kept between searches and stamped, a step's crossing, rips and displacements in a slot per state; `pathfinder.find`'s twin |
| `src/kernel/frontier.rs` | a search's open states: a heap by key and queued order, or buckets by exact integer key (the heap's order) when every cost is a dyadic fraction of the float scale |
| `src/kernel/tables.rs` | what every search reads and no search owns, registered from Python and versioned: the nets with their carriers, each carrier pair's sharing and crossing rule, the crossing units' shapes, every unit's facts, the reservations' carriers; `CarrierView`, one searching carrier's view of every net |
| `src/kernel/classify.rs` | `Query` (one search's own rules) laid out as a `View`; a layer's cells classified for every net at once, whole or one cell at a time (each wire with its net and its run on the cell, each unit and reservation by index) and priced for entry when a search reaches them; a crossing runs straight by the run's sides, and never with a unit on a unit wall |
| `src/kernel/layers.rs` | every searched layer's classification kept between searches and brought up to date by the cells each change touched (occupy, free, a run write, a unit's or a reservation's facts), with a checkpoint an undone attempt restores; classified whole on its first search and after a clear, a load or new nets |
| `src/kernel/records.rs` | the mirror of a world's records: the statics registered once (nets, pins, footprints, carriers, sharing, fields, needs, policies, orders) and each sync's changed placements, wires, units, attach tables and unit counter; the placements' port alternatives and the open attach cells per layer kept per sync |
| `src/kernel/overlay.rs` | maps read through to the records: an attempt's writes kept beside the mirror's wires, units and attach tables |
| `src/kernel/sim.rs` | the simulated world an attempt or a routing pass changes and undoes: the grid and its classified layers under an undo log, the overlays, the twins of the world's attach, unit and placing methods |
| `src/kernel/wiring.rs` | a wire's runs, set and removed, the unroute with its shared units, a displaced unit, a net's seed and standing lanes |
| `src/kernel/prefix.rs` | what a footprint may cover and displace, a wire's trim, the cell written with its attach tables, a net's readiness and span |
| `src/kernel/sweep.rs` | the fields' coverage and the square sweep that lays emitters again after a placement |
| `src/kernel/inspect.rs` | the inspection before a placement writes: rotation, region, overlap and displacement, ports shut and attach cells boxed in; `admits`, its cheap half over the mirror |
| `src/kernel/attempt.rs` | the native placement attempt: the inspection, the footprint's writes, the pack's legality handed in, the router's pending nets in its order, the routing pass, the fields laid again, every write undone |
| `src/kernel/route.rs` | the native routing pass: the lanes queued by the policy's order, each planned by `lay` and committed with its units and wire |
| `src/kernel/judge.rs`, `lanes.rs`, `plan.rs`, `lay.rs`, `spec.rs` | one net's lanes laid natively for the routing pass: the regions and crossing judgements, lane names and text, the plan under assembly, the worklist, the lay document |
| `src/pyo3_module.rs` | `kohakulayout_rs`: `parse_kl`, `write_kl`, `flatten`, `canonical`, `digest`, `Grid` (occupancy, runs, walls by key, the tables by `set_nets`, `set_pairs`, `set_shapes`, `note_unit`, `set_reservation`, `astar` over a query with the classification kept per layer and a carrier's view per rules version; `set_regions`; `register_records`, `route_pass`, `attempt` and `admits` over the mirror) |

## Building

```
cd src/kohakulayout-rs
VIRTUAL_ENV=../../.venv maturin develop --release
```

`KOHAKULAYOUT_BACKEND=python` forces the Python path everywhere; `native` makes a missing
module an error. `kl_check.py bench` requires the module.
