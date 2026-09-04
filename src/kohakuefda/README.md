# kohakuefda/

The library. Every subpackage is a stage of the pipeline or a shared model; the
CLI and the viewer are thin consumers. Dependency direction is one-way:
`data` → `model` → `flow` → `plan` → `layout` → `route` → `verify` → `render` → `cli`.
`model`, `flow` and `verify` never import `plan`, `layout` or `route`.

## Subpackages

| Package   | Responsibility                                                              |
| --------- | --------------------------------------------------------------------------- |
| `data/`   | Fetch pinned game tables (AKEData, mirror), wiki names, normalise, check    |
| `model/`  | Typed domain objects: items, machines, recipes, logistics, basements, rates |
| `i18n/`   | UI message bundles (`en`, `zh-TW`, `zh-CN`) and name lookup helpers        |
| `flow/`   | Steady-state flow graph, lane sizing, stability analysis, evaluation        |
| `plan/`   | Recipe selection, LP/MILP planner, cellization, netlist                     |
| `layout/` | Cell templates, basement geometry, placement, legalisation, chunking        |
| `route/`  | Two-layer occupancy grid and negotiated-congestion routing                  |
| `verify/` | Rule checker over plans and layouts, report model                           |
| `render/` | Rich tables, text grids, PNG, viewer bundle                                 |
| `cli/`    | `kohakuefda` command (typer + rich)                                         |

## Files

| File          | Description                     |
| ------------- | ------------------------------- |
| `__init__.py` | Package version                 |
| `__main__.py` | `python -m kohakuefda` dispatch |
| `log.py`      | `configure`: the `kohakuefda` logger's level and handlers (stderr, optional file) |
