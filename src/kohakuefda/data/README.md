# data/

Fetches the pinned game tables (mirror first because it inlines text, AKEData
as fallback and as the version index), pulls `zh-TW` names from the wiki, and
normalises everything into `data/<versionId>/dataset.json`. Also owns the
update checker that classifies a newer game version as blind-safe or
needs-handler, and importers for community layout formats.

## Files

| File                              | Description                                                       |
| --------------------------------- | ----------------------------------------------------------------- |
| `sources.py`                      | URLs, user agent, the list of tables the dataset needs            |
| `manifest.py`                     | AKEData manifest model and HTTP client factory                    |
| `mirror.py`                       | Hotfix id → mirror commit, raw table URLs                          |
| `fetch.py`                        | Download tables, write `source-manifest.json` with SHA-256, verify |
| `wiki_names.py`                   | `cnname` / `tcname` from wiki infoboxes, cached per version        |
| `icons.py`                        | Item, machine and logistics pictures from wiki `File:` pages into `<root>/icons/` with `index.json` |
| `check.py`                        | Classify a newer version (blind-safe vs needs handler), id diffs   |
| `reference.py`                    | Recorded wiki recipe modules against a dataset: keys with base names, `compare`, `fuel_differences`, `is_event` |
| `normalize/tables.py`             | Raw table loader and lenient field helpers                         |
| `normalize/ports.py`              | Table port transforms → grid ports (heading-based edge rule)       |
| `normalize/machines.py`           | `FactoryBuildingTable` + crafter modes → `Machine`                 |
| `normalize/items.py`              | `FactoryItemTable` + `ItemTable` → `Item`; `name_contents` names filled containers by their fluid |
| `normalize/recipes.py`            | Craft, group and crafter tables → `Recipe` with bindings           |
| `normalize/logistics.py`          | Belt/pipe/router/bridge/valve/conduit tables → units and constants |
| `normalize/basements.py`          | `static/basements.json` → `Basement`                               |
| `normalize/sinks.py`              | Sewage treatment tables → dump sinks                               |
| `normalize/power.py`              | Power station and fuel tables → `PowerStation`, `Fuel`             |
| `normalize/resources.py`          | `static/resources.json` → item id → source kind                    |
| `static/resources.json`           | Hand-maintained natural resources: ores, pumped fluids, vent gases |
| `normalize/build.py`              | Assemble the `Dataset`, attach wiki names, choose wiki titles      |
| `static/basements.json`           | Hand-maintained Core AIC Area squares and depot access per level   |
| `importers/industrial_planner.py` | IndustrialPlanner blueprint (schema 5) → `Layout`: tiles chained into segments, machine rotation offsets, recipe and pump-fluid matching by slug words, conduit links |

## Dependencies

- `kohakuefda.model`
- External: `httpx`
