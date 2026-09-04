---
title: CLI
summary: Every kohakuefda command and flag.
tags:
  - reference
  - cli
---

# CLI

`kohakuefda` is the installed console script; `python -m kohakuefda` is equivalent. Output is rich tables; stdout and stderr are UTF-8. Commands that produce a verdict exit with status 1 on an error finding, so they gate scripts.

Common options:

| Flag | Default | Meaning |
|---|---|---|
| `--root PATH` | `data` | Data root holding `<versionId>/dataset.json` and `raw/`. |
| `--version`, `-v ID` | newest built | Dataset version id to use. |
| `--lang en\|zh-TW\|zh-CN` | `en` | Language for names in tables. |
| `-V`, `--version` (top level) | | Print the tool's version. |
| `--verbose`, `-v` (top level, repeatable) | `0` | Log level: none is WARNING, once is INFO, twice or more is DEBUG. Logs go to stderr. |
| `--log-file PATH` (top level) | none | Also write DEBUG-level logs to this file. |

The top-level `-v` (before the subcommand) is `--verbose`; a subcommand's own `-v` (after the subcommand) is its `--version` option. `kohakuefda -v plan scenario.toml` runs at INFO; `kohakuefda plan scenario.toml -v 1.2.3` picks a dataset version.

## `data fetch`

```
kohakuefda data fetch [--version ID|latest] [--root PATH] [--source mirror|akedata] [--wiki/--no-wiki] [--refresh]
```

Resolve the version through the AKEData manifest, download the factory tables (`mirror` inlines names; `akedata` carries text hashes), verify the SHA-256 manifest, build `dataset.json`, fetch zh-TW names from the wiki (`--no-wiki` skips), rebuild with them. `--refresh` re-downloads cached tables.

## `data check`

```
kohakuefda data check [--root PATH] [--pinned ID]
```

Compare the newest published version against the pinned one (newest built by default) and classify the update as blind-safe or needs-handler.

## `data diff`

```
kohakuefda data diff OLD NEW [--root PATH]
```

Added and removed ids per collection between two built dataset versions.

## `data show`

```
kohakuefda data show [machines|items|recipes|logistics|basements] [-v ID] [--root PATH] [--lang L]
```

The dataset as a table.

## `data icons`

```
kohakuefda data icons [-v ID] [--root PATH] [--refresh]
```

Fetch the pictures of items, machines and logistics units from the game wiki into `<root>/icons/<kind>/<id>.png`, with `<root>/icons/index.json` naming what was found and what was not. Only missing pictures are fetched unless `--refresh`. The Studio shows a neutral glyph for anything without a picture.

## `glossary`

```
kohakuefda glossary [machines|logistics|items|all] [-v ID] [--root PATH] [--missing]
```

Names in en, zh-TW and zh-CN. `--missing` shows only rows without a zh-TW name.

## `plan`

```
kohakuefda plan SCENARIO.toml [-o plan.json] [-v ID] [--root PATH] [--lang L]
```

Plan the scenario: targets, machines, balances, nets, findings. Exit 1 when the plan is infeasible.

## `netlist`

```
kohakuefda netlist SCENARIO.toml [-o netlist.json] [-v ID] [--root PATH] [--lang L]
```

Plan, then build one cell per machine and the nets between their pins. Prints cells, nets and findings. Exit 1 on a netlist error or an infeasible plan.

## `layout`

```
kohakuefda layout SCENARIO.toml [-o DIR] [--seed N] [--iterations N] [--time-budget S] [--png] [--frames] [-v ID] [--root PATH]
```

Run the whole pipeline. Writes `plan.json`, `netlist.json`, `placement.json`, `layout.json`, `evaluation.json` and `report.json` (and `layout.png` with `--png`, which needs matplotlib) into `DIR` (default `out`). `--frames` also writes `frames/layout.json`, the recorded build, improve and final frames. Prints the grid, the modules, the utilisation table and the findings. `--seed` fixes the engine's random choices; `--iterations` sets the improvement moves after construction (default 3000); `--time-budget` bounds the whole layout in seconds (default 30), and 0 lets it run the full step count, which makes a seeded run reproducible. A line the square cannot hold is still written in a larger area and reported with `layout.too_big`. Exit 1 on any error finding.

## `check`

```
kohakuefda check LAYOUT [-o report.json] [--rates/--no-rates] [-v ID] [--root PATH]
```

Run the geometry rules and, unless `--no-rates`, the evaluator on a layout file. `LAYOUT` is our JSON or an IndustrialPlanner blueprint (detected by its `schemaVersion` and `entities` keys). Exit 1 on an error finding.

## `render`

```
kohakuefda render LAYOUT [--png FILE] [-v ID] [--root PATH]
```

Print the layout as a text grid; `--png` also writes a picture.

## `serve` (alias `view`)

```
kohakuefda serve [DIR] [--host ADDR] [--port N] [--open] [--workers N] [--no-api] [-v ID] [--root PATH]
```

Serve the web app over `DIR` (default `out`, created when missing): the viewer, the JSON and PNG artifacts of `DIR`, the dataset they name, and the run API that plans, places, routes and verifies scenarios stage by stage, keeping every run under `DIR/runs/<id>/`. Default host `127.0.0.1`; `--host 0.0.0.0` listens on every interface, so other machines on the network can open the app. Default port 8765; `0` picks a free port. `--open` opens the browser. `--workers` is the number of stages that may execute at once. `--no-api` serves the artifacts only. Exit 2 when the viewer bundle has not been built. The API routes are listed in [Frontend](../dev/frontend.md).
