---
title: Dataset
summary: What dataset.json holds, which game tables it is built from, how versions are pinned, and the hand-maintained basement table.
tags:
  - reference
  - data
---

# Dataset

`data/<versionId>/dataset.json` is the only game data the library reads. It is built by `kohakuefda data fetch` from published tables and checked in; a rebuild of the same version is byte-identical.

## Sources

- **AKEData manifest** (`https://data.akedata.wiki/manifest.json`): the version index. A version id is `<game version>@<hotfix>`.
- **`555me/beyondGameData`** on GitHub: the same tables with English and Simplified Chinese names inlined; the default source, because AKEData's tables carry text hashes in place of names.
- **endfield.wiki.gg**: Traditional Chinese names from each machine's and item's infobox, fetched through the wiki API with a few title aliases.

Tables pulled: the factory tables (buildings, items, crafts, craft groups, crafter modes, logistics, fluid consumption, sewage treatment, environment) plus the item, domain, tech node, panel store, level description and map id tables. Raw downloads and the SHA-256 manifest live under `data/raw/<versionId>/` and are not checked in.

## Contents

| Key | Content |
|---|---|
| `version` | `id`, `game_version`, `hotfix`, `source`, `published_at`. |
| `items{}` | `id`, `names{en, zh_tw, zh_cn}`, `phase` (1 solid, 2 liquid, 4 gas), `buffer_limit`, `value`, `storable`. Filled containers, which the game names like their empty container, carry the contents in the name: `Cuprium Bottle (Water)`. |
| `machines{}` | `id`, `names`, `kind`, `width`, `depth`, `height`, `ports[]` (`index`, `direction`, `type`, `x`, `y`, `edge`, `layer`), `power`, `needs_power`, `capacity_cost`, `modes[]`, `place_domains`, `recommend_domains`. |
| `recipes{}` | `id`, `names`, `machine_id`, `mode`, `group_id`, `inputs[]`, `outputs[]` (`item_id`, `count`), `seconds`, `env`, `buffers{}`, and the port bindings `belt_in`, `belt_out`, `pipe_in`, `pipe_out` (`buffer`, `ports[]`). |
| `logistics{}` | Belts, pipes, splitters, convergers, bridges, control ports and conduit ends: `kind`, size, `ms_per_round`, `volume`, `ports[]`, `capacity`. |
| `constants` | Belt and pipe rates, run limits, conduit distance, pipe unit limit, blueprint limits, control port limits per region, core power. |
| `basements{}` | Core AIC Areas: `region`, `hub`, `square_by_level`, `depot` (`fixed` with segments per level, or `laid` with ports and sections per level). |
| `activations{}` | Per machine: the activation item, `min_rate`, `max_rate`. |
| `dumps{}` | Per machine: the fluids it destroys, `rate_per_machine`, whether it is a fixed installation. |
| `env_gases{}` | Environment name to gas item. |
| `tech_names{}` | Names of tech nodes. |
| `resources{}` | Item id → where the world supplies it: `mine`, `pump_1`, `pump_2` or `gas_pump_1`. Hand-maintained in `data/static/resources.json`; the layout brings every fluid in by pipe from outside the area. |
| `pylons{}` | Per pylon machine: `reach` (cells beyond the footprint its square covers). |

Names fall back from zh-TW to zh-CN to English when a translation is missing.

## Port mapping

The tables describe ports in the machine's model space; the dataset maps them to grid cells with one rule (`x = position.x`, `y = depth − 1 − position.z`, heading to edge), and every port is checked to lie on the edge it faces. The rule is the calibration point when a new machine shape appears.

## Basements

`src/kohakuefda/data/static/basements.json` is hand-maintained from the wiki's outpost pages: the square per level and the depot access per depot level. Hub squares and Valley IV bus positions are not known yet and are marked so; see [Assumptions](../dev/assumptions.md).

## Versioning

`kohakuefda data check` compares the pinned version with the newest published one and classifies the difference as **blind-safe** (changes inside known schemas) or **needs handler** (new machine types, port shapes, modes, tables, constants or fields). Bumping the pinned version is an explicit change to the checked-in dataset.
