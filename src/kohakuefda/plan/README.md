# plan/

Turns a scenario into a plan: recipe graph expansion under region, gas, event
and ban rules with natural resources offered by default, the HiGHS MILP over
whole machines and crafts with explicit sinks, sources and zones per
environment, degrade-on-infeasible targets, exact balance rebuild, the power
draw reported, nets and cells; then the plan into one cell per machine with
its groups and a netlist, and the other plans a rival recipe or a ban would
give.

## Files

| File              | Description                                                                   |
| ----------------- | ----------------------------------------------------------------------------- |
| `recipes.py`      | `allowed` (region, gas, liquids, events, banned machines), `effective_supply` (natural resources per the scenario's defaults), `candidates`, `expand` → `RecipeGraph` |
| `lp.py`           | `solve`: whole machines and crafts per recipe over rated and open targets; activation per machine or per duty; zones per environment by footprint (`ZONE_FILL`); three-phase objective; optional area budget; `machine_cost`, `unit_cost`, `reference_rate` |
| `planner.py`      | `plan(dataset, scenario) -> Plan`: `resolve_targets`, `area_budget`, uses, exact balances, dump units, `power_draw`, zones, cells |
| `outcomes.py`     | `requirements`, `outcomes`, `next_products`                                   |
| `alternatives.py` | `alternatives` (a feasible plan per rival recipe of a used product), `bannable` (machines whose ban keeps the targets feasible) |
| `zones.py`        | `member_fits`, `group_fits`, `assign_zones`: which Gas Dispersing Unit each environment machine belongs to |
| `machines.py`     | `instantiate`: one cell per machine (`recipe_cell`, `dump_cell`, `zone_cell` heading a `zone<n>` group), outside inputs (`entry_cell`), the core (`core_cell`, `parked_core`), Depot Bus parts (`bus_part`) and bricks (`brick_cell`) in the `bus` group or on Valley IV slots; lane packing (`lane_groups`, `supply_lanes`); `CellFactory` |
| `netlist.py`      | `build_netlist`: one net per item over cell pins, planned vs nominal rates, trunk lanes, depot-via eligibility, `brick_count`, findings |

## Dependencies

- `kohakuefda.model`, `kohakuefda.flow`, `kohakuefda.layout`
- External: `highspy`
