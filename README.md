# KohakuEFDA

**End Field Design Automation.** An offline planner and layout generator for
the Automated Industry Complex (AIC) factory in *Arknights: Endfield*. Give it
your material supply rates, the products and rates you want, and which
basement (Core AIC Area) you are building in; it plans recipes and machine
counts, sizes belts and pipes, places machines, routes the logistics, checks
every rule the game enforces, and renders the result as text, PNG or an
interactive web view. It reads only static game data and never touches the
game itself.

## Why a layout generator

Ratio calculators tell you how many machines you need. They do not tell you
where to put them, how many belts a 30/min lane can feed, which outputs must be
bottled or stored before back-pressure stalls the line, or how the depot bus
and Protocol Capacity of your particular basement constrain the design.
KohakuEFDA models those rules directly, then solves placement and routing under
them.

## Install

```bash
uv pip install -e .            # library + CLI
uv pip install -e ".[cpsat]"   # exact placement for small instances (OR-Tools)
uv pip install -e ".[viz]"     # PNG rendering (matplotlib)
```

Python 3.13 or newer. Works on Windows, macOS and Linux.

## Quickstart

```bash
kohakuefda --version
kohakuefda data fetch                      # pinned game tables → data/<versionId>/dataset.json
kohakuefda data icons                      # item and machine pictures from the wiki → data/icons/
kohakuefda plan  scenario.toml             # recipes, machine counts, lanes, stability
kohakuefda netlist scenario.toml           # cells (rows of machines) and the nets between them
kohakuefda cell  <recipe_id> -n 3          # one row, rendered and validated in a harness
kohakuefda layout scenario.toml -o out/    # placed and routed layout
kohakuefda check  out/layout.json          # rule report
kohakuefda render out/layout.json --png    # pictures
kohakuefda serve  out/ --open              # the Studio: design, build, watch, tune and rerun in the browser
```

## Layout of the repository

| Path                     | What                                                        |
| ------------------------ | ----------------------------------------------------------- |
| `src/kohakuefda/`        | the library and CLI                                         |
| `src/kohakuefda-viewer/` | the Studio web app (Vue 3, JavaScript)                      |
| `data/`                  | normalised game dataset, versioned by game hotfix           |
| `tests/`                 | pytest suite                                                |
| `docs/`                  | public documentation                                        |

## Documentation

`docs/en/README.md` is the home: tutorials, guides, concepts (the factory model,
planning, rows and netlists, placement and routing, verification, a trilingual
glossary), reference (CLI, scenario file, artifacts, rules, dataset) and
development notes. `docs/zh-TW/` and `docs/zh-CN/` carry the localised landing
pages.

## Development

See `CONTRIBUTING.md` for the check suite and `CLAUDE.md` for the rules.

## Licence

Apache-2.0. Game data, names and mechanics belong to Hypergryph / Gryphline;
this project ships only normalised numbers and identifiers derived from
community data sources and is not affiliated with the game's publisher.
