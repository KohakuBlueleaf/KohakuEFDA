---
title: Getting started
summary: Install KohakuEFDA, fetch the pinned game dataset, and run every command once.
tags:
  - guides
  - install
  - getting-started
---

# Getting started

## 1. Install

Python 3.13 or newer. From a clone of the repository:

```bash
uv venv --python 3.13
uv pip install -e .                    # library and the kohakuefda command
uv pip install -e ".[viz]"             # plus matplotlib for PNG renders
uv pip install -e ".[dev]"             # plus pytest, ruff, black
```

Verify:

```bash
kohakuefda --version
```

`python -m kohakuefda` is equivalent to `kohakuefda`.

The viewer is a Vue application built once into the Python package:

```bash
cd src/kohakuefda-viewer
npm install
npm run build          # writes src/kohakuefda/web_dist/
```

Without that build `kohakuefda serve` prints the build command and exits.

## 2. The dataset

The repository ships a normalised dataset for one game version under `data/<versionId>/dataset.json`, so the tool works offline out of the box. To rebuild it, or to build one for a newer version, fetch the game tables:

```bash
kohakuefda data fetch                        # newest version published by AKEData
kohakuefda data fetch --version 1.5.3@9764758-3
```

The fetch downloads the factory tables from the community mirror (the AKEData tables carry text hashes rather than names; the mirror inlines the English and Simplified Chinese names), pulls Traditional Chinese names from the wiki, and writes `dataset.json` next to a SHA-256 manifest of the raw tables. Raw tables land under `data/raw/`, which is not checked in. Browse the result:

```bash
kohakuefda data show machines
kohakuefda data show recipes --lang zh-TW
kohakuefda glossary items --missing        # names without a translation
```

[Dataset updates](dataset-updates.md) covers version pinning and comparing versions.

## 3. Plan, netlist, layout

All planning starts from a scenario file. The repository's test fixtures are good first inputs:

```bash
kohakuefda plan    tests/fixtures/scenario_valley_battery.toml
kohakuefda netlist tests/fixtures/scenario_valley_battery.toml
kohakuefda layout  tests/fixtures/scenario_valley_battery.toml -o out/
```

`plan` prints recipes, machine counts, balances, nets and findings; `netlist` prints one cell per machine and the nets between their pins; `layout` runs the whole pipeline and writes `plan.json`, `netlist.json`, `placement.json`, `layout.json`, `evaluation.json` and `report.json` into `out/`. [First plan](../tutorials/first-plan.md) reads the tables line by line.

## 4. Check, render, view

```bash
kohakuefda check  out/layout.json
kohakuefda render out/layout.json
kohakuefda serve  out/ --open
```

`check` runs the geometry rules and the steady-state evaluator on any layout file, including one you edited or imported from IndustrialPlanner; `render` prints it as a text grid or writes a PNG; `serve` starts the web app over a directory: its artifacts, and scenarios run stage by stage in the browser ([Web app](viewer.md)).

## 5. Other ways to make it

The Studio's plan page lists every other recipe path the targets allow and the machines you could ban and still get a plan; pick one and it rebuilds. From the command line, put the recipe in `[recipe_overrides]` or the machine in `banned_machines` of the scenario file and run `plan` again.

## Where next

- [Scenarios](scenarios.md) for every field of the scenario file.
- [The pipeline](../concepts/foundations/the-pipeline.md) for what each stage decides.
- [CLI](../reference/cli.md) for every flag.
