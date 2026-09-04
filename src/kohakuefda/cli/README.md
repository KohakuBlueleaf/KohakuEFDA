# cli/

The `kohakuefda` command, built on typer with rich output. One handler module
per subcommand group; `__main__.py` holds the command tree.

## Files

| File             | Description                                                                 |
| ---------------- | --------------------------------------------------------------------------- |
| `__main__.py`    | Command tree, `--version`, `--verbose`/`-v` and `--log-file` (calls `kohakuefda.log.configure`), utf-8 stdio, `main()` |
| `data.py`        | `data fetch` / `check` / `show` / `icons`, dataset loading helpers          |
| `diff.py`        | `data diff <old> <new>`                                                     |
| `glossary.py`    | `glossary [machines|logistics|items|all] [--missing]`                       |
| `plan.py`        | `plan scenario.toml [-o plan.json] [--lang]`                                |
| `layout_cmds.py` | `layout scenario.toml [-o out/] [--seed] [--iterations] [--optimizer] [--png] [--frames]` (writes plan, netlist, placement, layout, evaluation, report, frames), `check layout.json [-o report.json] [--no-rates]`, `render layout.json [--png out.png]`; IndustrialPlanner blueprints are detected and imported |
| `cells.py`       | `netlist scenario.toml [-o netlist.json] [--lang]`                          |
| `view.py`        | `serve <dir> [--host] [--port] [--open] [--workers] [--no-api]` (alias `view`): the web app from `kohakuefda.serve` over the directory, runs under `<dir>/runs/` |

## Dependencies

- Top of the graph; imports every stage it drives and `kohakuefda.serve`.
- External: `typer`, `rich`
