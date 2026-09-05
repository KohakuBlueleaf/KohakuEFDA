# kohakuefda-viewer/

The web viewer: Vue 3 (`<script setup>`), Pinia, Vite, UnoCSS, file-based
routes from `src/pages/` through unplugin-vue-router, auto-imported Vue and
Pinia APIs, auto-registered components from `src/components/`. JavaScript
only. `npm run build` writes into `../kohakuefda/web_dist/`, which
`kohakuefda view <dir>` serves next to the JSON artifacts of `<dir>`
(`artifacts/index.json` lists them) and the dataset (`dataset.json`).

## Files

| Path                             | Description                                                      |
| -------------------------------- | ---------------------------------------------------------------- |
| `index.html`                     | Vite entry                                                       |
| `vite.config.js`                 | Plugins, alias `@`, build output into `web_dist/`                |
| `uno.config.js`                  | UnoCSS presets (wind3, attributify, icons)                       |
| `src/main.js`                    | App, Pinia, hash-history router from auto routes                 |
| `src/App.vue`                    | Shell: title, page links, language switch, loads the artifacts   |
| `src/pages/index.vue`            | Loaded files and the scenario summary                            |
| `src/pages/dataset.vue`          | Machines, recipes and items with a text filter                   |
| `src/pages/plan.vue`             | Flow graph, targets, recipes, balances, nets, findings           |
| `src/pages/layout.vue`           | Canvas grid with layer toggles, zoom, modules, hover details     |
| `src/pages/modules.vue`          | Build order of blueprint-sized modules                           |
| `src/pages/report.vue`           | Every finding of the layout report                               |
| `src/components/DataTable.vue`   | Generic table with column labels and a filter                    |
| `src/components/FindingsTable.vue` | Findings coloured by severity                                  |
| `src/components/PlanGraph.vue`   | SVG graph of recipe nodes and item edges ranked by longest path  |
| `src/components/LayoutCanvas.vue` | Canvas2D renderer of machines, ports, belts, pipes, units, modules |
| `src/stores/app.js`              | Language, artifact loading state, dataset                        |
| `src/i18n/`                      | `useI18n()`, the `en`, `zh-TW`, `zh-CN` bundles, `names.js` (dataset names, rate formatting) |
| `src/style.css`                  | Theme variables                                                  |

The stage inspector reads registered solver names from `/api/solvers` and
backend/budget settings from `/api/params`. Extra solver settings use the
`solver_options` JSON field. Labels exist in all three supported locales.

## Commands

```bash
npm install
npm run dev
npm run build
npm run lint
npm run format:check
```
