# model/

Typed domain objects: items with phase, machines with footprint and ports,
recipes with port bindings, logistics units and constants, basements, the
scenario, the dataset container, plans, layouts, cells and netlists, and
`Fraction`-per-minute rates. Pure data; no solving and no I/O beyond loading
and saving its own files.

## Files

| File           | Description                                                                 |
| -------------- | --------------------------------------------------------------------------- |
| `base.py`      | `EfdaModel`: pydantic base with strict fields                               |
| `rates.py`     | `Rate` (exact `Fraction` per minute), `per_minute`, `lanes_needed`, belt/pipe constants |
| `names.py`     | `Names` (en / zh-TW / zh-CN) with fallbacks, `Lang`                         |
| `geometry.py`  | `Edge`, rotations of cells, edges and sizes, `edge_step`                    |
| `items.py`     | `Item`, `Phase`                                                             |
| `machines.py`  | `Machine`, `Port`, `Mode`, `PortType`, `PortDir`, layer constants           |
| `recipes.py`   | `Recipe`, `Stack`, `Binding`, per-item rates and output-port lookup         |
| `logistics.py` | `LogisticsUnit`, `LogisticsConstants`                                       |
| `basement.py`  | `Basement` (with `square_or_default`), `Region`, `FixedBus`, `LaidBus`, `BusSegment`, `DEFAULT_SQUARE` |
| `sinks.py`     | `Activation`, `DumpSink`, source rates, zone gas rate and machine ids       |
| `power.py`     | `Pylon` (reach and `coverage`)                                              |
| `dataset.py`   | `Dataset` (with `resources`, `pylons`, `is_resource`, `is_gas`), `DatasetVersion`, load/save, recipe lookups |
| `scenario.py`  | `Scenario` (targets as a rate, `min` or `max`; `gas`, `liquids`, `events`, `banned_machines`, `area_fill`, `natural_default`, `gas_default`, `activation`, `depot`), `BasementRef`, `PlanMode`, `DepotMode`, `goal_of`, TOML reader and writer |
| `plan.py`      | `Plan` (with `zones`), `RecipeUse`, `ItemBalance`, `Net`, `Cell`, `Finding`, `TargetResult` (with `goal`) |
| `layout.py`    | `Layout` (grid plus `area`, the Core AIC Area inside it; `area_rect`, `origin`, `entries`), `Placed`, `Unit`, `Segment` (with `heading`, `entry`, `item_id`), `Entry` (an outside input on the border), `Link`, `Rect` |
| `cells.py`     | `Pin` (with `alternatives`), `Fragment` (one machine), `CellInstance` (with `env`, `group`, `constraint`), `BUS_GROUP`, `PinRef`, `NetSpec`, `Netlist` |
| `placement.py` | `Placement` (grid, area, gap, pylons, entries, cost terms), `PlacedBlock` (with chosen `ports`): the layout stage's checkpoint |
| `control.py`   | `Observe` and `Cancelled` callables for long loops, `CancelledError`        |

| `solver.py` | Immutable Problem, Snapshot, Action, Scope, Assessment, Candidate and SolveEvent/SolveResult records |

## Dependencies

- External: `pydantic`
