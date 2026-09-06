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
| `src/layout-settings.js`         | Catalog field schema, typed request serialization, effective limits and legacy outcome interpretation |
| `src/layout-settings.test.js`    | Control completeness, types, solver switching, SSR rendering and outcome tests |
| `src/components/flow/StageInspector.vue` | Stage execution, progress and search outcome panel |
| `src/components/flow/LayoutSettings.vue` | Primary budgets, typed solver controls, presets and advanced sections |
| `src/components/flow/SettingField.vue` | Shared typed number, checkbox, text and select control |
| `src/components/flow/LayoutOutcome.vue` | Search stop reason, retained result and effective last-run settings |

The stage inspector reads solver defaults, parameter types and parallel capability
from `/api/solvers`; shared backend/budget settings come from `/api/params`.
Time/actions, backend, seed and policy stop controls are always visible. Advanced
sections include construction insertion lookahead and optional frontier/local-repair
controls, as well as every remaining selected-solver field, serialized as typed values
in `solver_options`; the optional JSON editor edits those same overrides. Solver
switching preserves separate drafts. Time presets explicitly enable budget-driven
search and remove action caps, but do not silently enable a zero-step phase.

HC/SA budget/step semantics and serial execution are shown next to the controls;
baseline workers/spread settings are hidden for other policies. Final outcomes
separate `incomplete` search from execution `failed` and preserve a successful
`done` result even when search ends by budget exhaustion. All three locales have
control and outcome labels. HC/SA frames report current; the selected artifact is
best routed. Partial diagnostic artifacts are labelled incomplete, not complete.

## Dependencies

- Vue 3, Pinia, Vite, UnoCSS, unplugin-vue-router and auto-import/component plugins.
- Backend `/api/params` and `/api/solvers` contracts; no game-model facts embedded in controls.

## Commands

```bash
npm install
npm run dev
npm run build
npm run lint
npm run format:check
```
