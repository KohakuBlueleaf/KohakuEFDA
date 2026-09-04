---
title: Artifacts
summary: The shape of every JSON file the tool writes: plan, netlist, placement, layout, evaluation, report, frames.
tags:
  - reference
  - artifacts
  - json
---

# Artifacts

Every artifact carries `schema_version` and `dataset_version`. Rates are exact fractions serialised as strings (`"30"`, `"45/2"`); cells are `[x, y]` pairs; edges are `"N"`, `"E"`, `"S"`, `"W"`; rotations are `0`, `90`, `180`, `270` clockwise. Findings everywhere have the shape `{rule, severity, subject, message}` with severity `info`, `warning` or `error`.

## `plan.json`

| Field | Content |
|---|---|
| `scenario` | The scenario, `"unlimited"` written as `null`; targets may be `"min"` or `"max"`. |
| `status` | `ok`, `degraded` or `infeasible`. |
| `scale` | Common factor the rated targets were scaled by (`"1"` when met). |
| `targets[]` | `item_id`, `requested` (the resolved rate), `achieved`, `goal` (`min`, `max` or `null`). |
| `recipes[]` | `recipe_id`, `machine_id`, `mode`, `crafts_per_min`, `machines_exact` (the load in machine-equivalents), `machines` (whole machines built). Dump units appear as `recipe_id: "dump:<machine>"`. |
| `zones{}` | Environment → number of Gas Dispersing Unit zones the plan counted. |
| `items{}` | Per item: `produced`, `consumed`, `supplied`, `delivered`, `sunk`, `sink_kind` (`depot`, `dump` or null), `net`. |
| `nets[]` | `item_id`, `source`, `target` (recipe ids, or `supply`, `target`, `depot`, `dump`), `rate`, `fluid`, `lanes`, `lane_capacity`. |
| `cells[]` | `recipe_id`, `machine_id`, `mode`, `count`, per-machine `inputs{}` and `outputs{}`. |
| `findings[]` | Plan and stability findings. |
| `power`, `footprint_cells`, `machine_count` | Totals over every machine including dump units; `power` is the draw the pylons must carry. |

## `netlist.json`

| Field | Content |
|---|---|
| `scenario`, `plan_status` | As in the plan. |
| `cells[]` | One per machine. Each has `width`, `height`, `machines[]` (one placed machine at the origin, none for an outside input), `id`, `kind` (`recipe`, `dump`, `unloader`, `loader`, `entry`, `zone`, `depot`, `core`), `machine_id`, `recipe_id`, `pins[]`, `env` (the environment a recipe needs or a zone creates), `group` (`bus`, `zone<n>` or `null`), `constraint` (`free` inside the area, `edge` on its border, `slot` on a fixed bus slot, `park` anywhere out of the way). |
| `cells[].pins[]` | `id`, `direction` (`in`/`out`), `kind` (`belt`/`pipe`), `item_id`, `rate`, `cell`, `edge` (the default port), `alternatives[]` of `{index, cell, edge}` (every port the lane may use). |
| `nets[]` | `id`, `item_id`, `kind`, `rate` (planned), `nominal` (sum of sink lane rates), `trunk_lanes`, `sources[]` and `sinks[]` of `{cell_id, pin_id, rate}`, `via_depot_ok`. |
| `findings[]` | Netlist findings. |

## `placement.json`

The layout stage's checkpoint: where every block ended up.

| Field | Content |
|---|---|
| `square` | `[width, height]` of the Core AIC Area. |
| `grid` | `[width, height]` of the whole grid: the area plus its ring. |
| `area` | `[x0, y0, x1, y1]` of the area inside the grid. |
| `gap` | Kept at 0; machines may share an edge, and the cell a connection needs is a routed wire. |
| `cost`, `terms{}` | The rectangle area of the result and its terms (`area`, `width`, `height`, `waste`, `length`, `junctions`, `pylons`, `bricks_underused`). |
| `blocks[]` | `id` (a cell id), `x`, `y`, `rotation`, unrotated `width` and `height`, `ports{}` (pin id → index of the alternative port it uses; absent means the default). |
| `pylons[]` | Anchor cells of the pylons the engine derived. |
| `entries[]` | Outside inputs: `id`, `item_id`, `rate`, `x`, `y`, `edge` (the border they enter from). |
| `findings[]` | Board and engine findings. |

## `layout.json`

| Field | Content |
|---|---|
| `basement` | `region`, `basement_id`, `level`, `depot_level`. |
| `width`, `height` | The grid: the Core AIC Area plus its ring. |
| `area` | `[x0, y0, x1, y1]` of the Core AIC Area inside the grid, or `null` when the whole grid is the area (hand-built and imported layouts). |
| `machines[]` | `id`, `machine_id`, `x`, `y`, `rotation`, `mode`, `recipe_id`, `config{}` (`item` for sources and conduit inlets, `rate` to override a source's rate, `out<index>` and `out<index>_rate` for the item an Automation-Core port supplies). |
| `units[]` | `id`, `unit_id` (a logistics id such as `log_splitter`), `x`, `y`, `rotation`, `config{}`. |
| `segments[]` | `id`, `kind` (`belt`/`pipe`), `cells[]` from source to sink, `heading` (an edge; meaningful for a single cell), `entry` (the outside input it starts from, or `null`), `item_id`. |
| `entries[]` | Outside inputs as in the placement. |
| `links[]` | `inlet`, `outlet`: ids of a Conduit Inlet and Outlet pair. |
| `modules[]` | `id`, `x`, `y`, `width`, `height`, `entities[]` (ids anchored inside). |
| `notes` | Free text; the pipeline writes the basement, level, seed and time budget. |

Machines in a generated layout are named `<cell id>:m0` and pylons `pylon<n>`; units `w<n>:split`, `w<n>:join`, `bridge:<x>:<y>:<kind>` and `w<n>:rep…` come from the router; segments are `w<n>:p<n>`.

## `evaluation.json`

| Field | Content |
|---|---|
| `segments{}` | Per segment id: `items{}` (rate per item), `total`, `capacity`. Direct links appear as `link:<owner>:<port>:<edge>`. |
| `machines{}` | Per placed id: `machine_id`, `recipe_id`, `utilisation`, `inputs{}`, `outputs{}`, `stalled_by`. Machines without ports (pylons, bus parts) are absent. |
| `iterations`, `converged` | How the relaxation ended. |

## `report.json`

| Field | Content |
|---|---|
| `subject` | The file checked, or the basement and level for a generated layout. |
| `findings[]` | Geometry, rate, netlist and layout findings. |

A report is `ok` when no finding has severity `error`.

## Frames

`kohakuefda layout --frames` and every run of the web app record the layout stage as a JSON list, `frames/layout.json`:

- one `catalogue` frame: `grid`, `area`, `slots[]` as `[x, y, side]`, and `blocks[]` with `id`, `kind`, `constraint`, `group`, `env`, `powered`, `width`, `height`, local `machines[]` and `pins[]` with their `alternatives[]`;
- `search` frames every `frame_every` moves: `restart`, `step`, `cost`, `best`, `blocks[]` as `[id, x, y, rotation]`, `rect` (the packed rectangle);
- `detail` frames per round of the detailed pass: `candidate`, `round`, `blocks[]`, `rect`, `pylons[]` as `[x, y]`, `entries[]` as `[id, x, y, edge]`, `wires[]` as `[id, kind, net, cells]`, `overused[]` as `[layer, x, y]`, `failed[]` wire ids, `clean`;
- one `final` frame: `blocks[]`, `pylons[]`, `entries[]`, `terms{}`, `fits`.

## Run directories

The web app keeps each run under `runs/<id>/`: `run.json` (id, creation time, per-stage status, parameters, timing and error), `scenario.toml`, the checkpoints above as they are produced, and `frames/`.

## `dataset.json`

Described in [Dataset](dataset.md).
