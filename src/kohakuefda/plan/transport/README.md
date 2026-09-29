# plan/transport

An optional transport-aware operating point, before placement. `allocate` jointly
chooses activity per solid-only recipe instance and direct belt lanes. `materialize`
turns a feasible result into ordinary project cells and nets; the existing synth and
KohakuLayout pipeline consume them without a second geometry model.

The recipe-level plan is unchanged. Whole recipe activity, material marginals,
physical port domains and lane capacities are checked again with exact fractions
before an allocation is accepted. An allocation is not a routed-throughput certificate.

## Files

| File | Description |
|---|---|
| `model.py` | `Transfer`, `TransportResult`, `TransportError` and the source-netlist fingerprint |
| `solve.py` | Bounded HiGHS allocation, rational reconstruction and exact feasibility checks |
| `domains.py` | Recipe-compatible port domains, Hall capacity inequalities and injective matching |
| `materialize.py` | Independent capacity-bounded physical lanes with compatible pin alternatives |
| `__init__.py` | Public allocation and materialization API |

## Contract

`build_netlist(..., transport="direct")` (the netlist stage's `transport`) builds the
rated netlist (per-instance activity, full lanes before partial lanes, conservation
across conduit links), allocates on it and materialises the result; `rated` stops
before allocating and `legacy` is the default.

The allocator preserves the total activity of each recipe, but may redistribute it
among its instances. Recipes with fluid pins retain their declared activity. The
objective minimizes the count of direct solid lanes. It does not optimize mixed
belts, split/merge trees, pipe topology, geometry or the startup sequence.

A result with `feasible=False` carries a reason and is not materialized. A result may
be feasible without optimality when the time limit interrupts the MIP. Reconstructed
flows are checked independently of the optimizer's floating-point status. Port
compatibility is checked both with domain inequalities and actual matching.

`materialize` rejects a result from a different source-netlist fingerprint. It returns
a deep copy and clears reusable-unit labels on affected cells: changed instance duties
or topology cannot silently reuse an old identical-tile claim.

## Dependencies

- `kohakuefda.model`: project netlists, dataset, port definitions and findings.
- `kohakuefda.plan.operating`: exact capacity-packed rates.
- `highspy`: the existing MILP dependency; parallel solving is disabled per worker.
- No geometry or rendering dependency, and no imports from KohakuLayout.
