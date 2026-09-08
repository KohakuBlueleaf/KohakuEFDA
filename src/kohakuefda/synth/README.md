# kohakuefda.synth

The project netlist as a KohakuLayout problem. The planner and `plan/machines.py` keep
producing the project `Netlist`; the synth turns it into a framework `Problem` for the
Endfield pack, and a framework `Layout` back into the project's
`Placement` and `Layout`.

| file | what |
|---|---|
| `footprints.py` | `footprint_of(machine)`: size from the dataset, every port as a side and offset, machines shade the sky; `ENTRY_FOOTPRINT` for outside inputs; `library_of(dataset, cells)`; `ports_for(fp, pin)`: the pin's default port first, then its alternatives |
| `flows.py` | `Flows`, the wire analysis `Translation` inherits: the net's graph and potential, the flow on every step from the lane facts, interior terminals and junction cells, each junction's kind and rotation from the flows meeting there (a unit the router placed where the flow passes straight through keeps its kind: a repeater is a splitter with one output), pieces oriented by flow with dead pieces dropped; `step_between` and the unit-kind sets |
| `layout.py` | `layout_of(problem, layout, dataset, netlist, assessment)`: a framework layout back into the project's `Placement` and `Layout`; `Translation(Flows)` emits units with computed kinds and rotations, segments with entry and heading, pylons, entries, blocks and the terms |
| `frames.py` | `FrameObserver` (framework events to the project's schema-1 frames, plus the `catalogue` and `final` frames), `LayoutEveryFrame` (a frame with the layout every N charged mutations, and a layout on every frame the solver sends), `Cancel` (the run manager's flag raised at the next attempt) |
| `problem.py` | `problem_of(dataset, netlist, board)`: cells with pins, constraints, groups and `needs`, machine facts in `attrs["endfield"]`; project nets paired into lanes (`lanes_of`, `assign`) and each connected set of lanes one framework net (`components`, `nets_of`); groups; the basement as fabric params (`params_of`); `kl_id` and `project_pin_id` map pin ids |

Dependencies: `kohakulayout` (`ir`, `engine.plugins`), `kohakuefda.model`, `kohakuefda.layout` (`board`, `fragments`, `place`), `kohakuefda.physics`.
