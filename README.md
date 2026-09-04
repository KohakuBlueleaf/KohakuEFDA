# KohakuEFDA

**End Field Design Automation.** An offline planner and layout generator for the
Automated Industry Complex (AIC) in *Arknights: Endfield*. You give it the
products and rates you want, what you already have coming in, and which basement
(Core AIC Area) you are building in. It plans the recipes and machine counts,
sizes the belts and pipes, places every machine, routes every lane, checks every
rule the game enforces, and hands back a layout you can build — as a text grid, a
PNG, or an interactive web app.

It reads static game data only. Nothing is injected into the game, and nothing is
read out of it.

## Why

Ratio calculators tell you how many machines you need. They do not tell you where
to put them — how many belts a 30/min lane feeds, which outputs stall the line
through back-pressure, whether a pylon reaches the machine you just moved, or how
many bricks your basement's depot bus actually seats. KohakuEFDA models those
rules and then solves placement and routing under them.

Every in-game number it relies on is recorded with its source in
`.internal/game-knowledge/` and cited by id in the code and docs (`LOG-01`,
`COV-02`, `DEP-18`, …).

## Install

Python 3.13 or newer, on Windows, macOS or Linux.

```bash
uv venv --python 3.13
uv pip install -e .              # library and the kohakuefda command
uv pip install -e ".[viz]"       # + matplotlib, for PNG output
uv pip install -e ".[dev]"       # + pytest, ruff, black
```

Two parts are **built separately** and neither is checked into the repository.

### The web app

`kohakuefda serve` refuses to start without it:

```bash
cd src/kohakuefda-viewer
npm install
npm run build                    # writes src/kohakuefda/web_dist/
```

### The native routing grid (optional, but you want it)

The routing grid and its A\* have a Rust implementation. It is optional — without
it the pure-Python search runs and gives the same layouts — but it is worth
**about 10× the whole run**, so build it unless you have a reason not to.

The package's build backend is setuptools, so `pip install -e .` does *not* build
the crate. Use maturin:

```bash
uv pip install -e ".[native]"    # installs maturin
maturin develop --release        # builds the crate into the venv
```

Check it took:

```bash
python -c "import kohakuefda.route.pathfinder as p; print(p.NATIVE)"   # True
```

Two things that bite on the way:

- **`Both VIRTUAL_ENV and CONDA_PREFIX are set`** — maturin refuses to guess.
  Unset one (`unset CONDA_PREFIX`) and run it again.
- **`failed to copy … (os error 32)` on Windows** — a Python process is holding
  the old extension open. The layout search runs worker processes; if one is
  still alive from an interrupted run, stop it and rebuild.

See [the native routing grid](docs/en/dev/native.md) for what moved into Rust and
how it is held to the Python implementation.

## Quickstart

```bash
kohakuefda --version
kohakuefda layout tests/fixtures/scenario_valley_battery.toml -o out/
kohakuefda render out/layout.json
kohakuefda serve  out/ --open
```

That lays out one of the bundled scenarios and opens the Studio on the result. A
normalised dataset for one game version ships in `data/`, so this works offline
straight from a clone.

Every command:

```bash
kohakuefda plan     scenario.toml          # recipes, machine counts, lanes, stability
kohakuefda netlist  scenario.toml          # the cells and the nets between their pins
kohakuefda layout   scenario.toml -o out/  # the whole pipeline; writes every artifact
kohakuefda check    out/layout.json        # rules and steady-state rates for any layout
kohakuefda render   out/layout.json --png  # text grid, or a picture
kohakuefda serve    out/ --open            # the Studio: design, run, watch, tune, rerun
kohakuefda data     fetch                  # rebuild the dataset from the pinned tables
kohakuefda glossary items                  # the trilingual name table
```

`kohakuefda layout --help` lists the search settings; the useful ones are
`--attempts` (how many complete layouts to try) and `--workers`.

## How it works

Four stages, each writing an artifact you can read, edit and re-enter:

| Stage | Decides |
|---|---|
| **plan** | Which recipes, how many of each machine, what rate every lane carries |
| **netlist** | Machines as cells with pins, and the nets that join them |
| **layout** | Where every machine stands and where every belt and pipe runs |
| **verify** | The geometry rules, and the steady state the line settles at |

The layout stage is the interesting one. A layout is **whole or it is nothing**:
every machine standing, every lane routed. Placing a machine and routing its
belts are one operation — a position that cannot be wired never exists — so the
search never passes through a broken layout.

- **Spread.** Machines go into the squares of a lattice whose step is derived,
  not tuned: the widest machine plus the one cell a connection always costs
  (LOG-11). Clearance is per edge — one free cell where a wired port sits, none
  where no port does, because machines may share edges (PLC-01). They are laid in
  the order the flow visits them, each chain walked to its end, and the squares
  in a serpentine, so a machine lands beside the one that feeds it.
- **Shrink.** The room comes back out: lines nothing stands on deleted, sides
  pressed to a wall, machines pulled toward what they feed. Every step only
  *removes* space, so it can never strand a machine or a lane.
- **Search.** The spread is deterministic once three choices are fixed — the
  laying order, the corridor width, the direction of the walk — so those are a
  genome and the spread is its decoder. Three searches run over that space
  (annealing, evolution, independent draws); none wins on every factory, so by
  default they are dealt out across the cores and the best result is kept.

Runs are reproducible: the same seed and settings give the same layout, whatever
the machine load.

## Repository

| Path | What |
|---|---|
| `src/kohakuefda/` | the library and CLI — `data model flow plan layout route verify render cli` |
| `src/kohakuefda-rs/` | the Rust routing grid and A\* (PyO3, optional) |
| `src/kohakuefda-viewer/` | the Studio web app (Vue 3, JavaScript) |
| `data/<versionId>/` | the normalised dataset and its manifest, versioned by game hotfix |
| `docs/` | public documentation, in `en`, `zh-TW` and `zh-CN` |
| `tests/` | the pytest suite and its fixtures |

## Documentation

`docs/en/README.md` is the home. Tutorials and guides for getting a first plan
out; concepts for the factory model, planning, cells and netlists, placement and
routing, and verification; reference for the CLI, the scenario file, the
artifacts and the rules; development notes including
[the native routing grid](docs/en/dev/native.md) and the
[dependency graph](docs/en/dev/dependency-graph.md). `docs/zh-TW/` and
`docs/zh-CN/` carry the localised landing pages.

## Development

```bash
black . && ruff check .
python scripts/dev/comment_budget.py src scripts tests
pytest -q
cargo test                                    # the crate's own tests
cd src/kohakuefda-viewer && npm run lint && npm test && npm run build
```

`CONTRIBUTING.md` has the full check suite; `CLAUDE.md` has the house rules.

## Licence

Apache-2.0. Game data, names and mechanics belong to Hypergryph / Gryphline. This
project ships only normalised numbers and identifiers derived from community data
sources, and is not affiliated with the game's publisher.
