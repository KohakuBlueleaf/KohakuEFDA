---
title: Scenario file
summary: Every field of scenario.toml with its type and default, including rate-free targets and the area budget.
tags:
  - reference
  - scenario
---

# Scenario file

A TOML file. Scalar keys come first; tables follow. Item and recipe ids are the game's internal ids as found in the dataset. The Studio writes and reads the same file.

```toml
mode = "balanced"
mixed_lanes = true
gas = true
liquids = true
events = false
natural_default = "plenty"
gas_default = "none"
activation = "built"
banned_machines = ["transmuter_1"]
area_fill = 0.5

[supply]
<item_id> = <rate> | "unlimited"

[targets]
<item_id> = <rate> | "min" | "max"

[basement]
region = "valley4" | "wuling"
basement_id = "<id>"
level = 1
depot_level = 1

[recipe_overrides]
<item_id> = "<recipe_id>"
```

| Field | Type | Default | Meaning |
|---|---|---|---|
| `mode` | `area` \| `machines` \| `balanced` | `balanced` | Cost tie-break once targets are met: fewest machines, smallest area, or both. |
| `mixed_lanes` | bool | `true` | Allow one belt to carry several items into a terminal sink. |
| `gas` | bool | `true` | Allow gas recipes, gas machines and environment-gated recipes. |
| `liquids` | bool | `true` | Allow fluid recipes and machines (pipes, crucibles, pumps). |
| `events` | bool | `false` | Allow limited-time event recipes (game-knowledge RCP-06). |
| `natural_default` | `plenty` \| `none` | `plenty` | Ores and, outside Valley IV, the world's liquids count as available without a `supply` entry (RES-01); `none` makes only listed items available. |
| `gas_default` | `plenty` \| `none` | `none` | Whether vent gases count as available without a `supply` entry. |
| `activation` | `built` \| `duty` | `built` | Charge a transmuter's activation fluid per built machine (ACT-03) or per machine-equivalent of duty. |
| `banned_machines` | list of machine ids | `[]` | Machines the player cannot build; their recipes are never used, so the plan takes another path when one exists. |
| `area_fill` | float | unset (0.5) | Fraction of the square machines may cover when a target is `"max"`. |
| `depot` | `bus` \| `core` | `bus` | Where solids cross the depot: Depot Bus bricks only, or the Automation-Core's own ports first (six out, fourteen in) and bricks for the rest. |
| `supply.<item>` | rate or `"unlimited"` | none | Units per minute available; `"unlimited"` marks a material without a cap; `0` removes a natural resource the defaults would offer. The tool sizes the bricks and the outside inputs. |
| `targets.<item>` | rate, `"min"` or `"max"` | none | A rate to deliver, absolute and degraded together when infeasible; `"min"` asks for the smallest whole-machine line that makes the item (one machine of its cheapest maker under the mode, fed properly); `"max"` asks for as much as the supply and the area budget allow. |
| `basement.region` | `valley4` \| `wuling` | required | Selects recipes, machines and depot geometry. |
| `basement.basement_id` | string | required | Outpost or hub id, e.g. `infra_station`, `sky_king_flats`. |
| `basement.level` | int | `1` | Square size. |
| `basement.depot_level` | int | `1` | Depot access: bus segments (Valley IV) or bus ports and sections (Wuling). |
| `recipe_overrides.<item>` | recipe id | none | The only recipe considered for that item. |

Rates are integers, decimals or fraction strings such as `"45/2"`; they are read as exact fractions.

The same object is embedded in `plan.json` and `netlist.json` under `scenario`, with `null` in place of `"unlimited"`. The plan's `targets[]` carry the resolved `requested` rate and the `goal` (`min`, `max` or `null`).
