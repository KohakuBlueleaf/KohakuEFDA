# tests/fixtures/

Test-owned data: small scenarios, dataset excerpts and layouts that the tests
control. Nothing here ships, and no test depends on the checked-in dataset
changing.

| File | Contents |
|---|---|
| `scenario_*.toml` | The planner's own scenario and the three benchmarks (`scenario_valley_battery`, `scenario_wuling_hetonite`, `scenario_gas_xiranite`), plus two recorded player scenarios (`scenario_wuling_battery4`, `scenario_wuling_script`) |
| `scenario_dense_*.toml` | Valley 6/12/18 and Wuling 6/12 batteries per minute; gas off, explicit zero wood, only listed natural supplies, expanded 70×70/80×80 areas (REG-04) |
| `industrial_planner_min.json` | A small IndustrialPlanner blueprint for the importer |
| `wiki_recipes.json` | Every `Module:Recipe/<facility>` data module of endfield.wiki.gg, parsed; refresh with `python scripts/dev/wiki_recipes.py fetch` |
