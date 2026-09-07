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
| `src/style.css`                  | Theme variables and layout styling |
| `src/progress.js`                | Versioned/legacy frame interpretation, frame-specific geometry and elapsed-time curves |
| `src/progress.test.js`           | Status, SSE ingestion, SSR labels, timeline and legacy compatibility tests |
| `src/progress-canvas.test.js`    | Canvas drawing commands across expansion and historical playback |
| `src/progress-draw.js`           | Materialized progress layout and workspace/target boundary rendering |
| `src/components/flow/LayoutProgress.vue` | Selected-frame phase, current/best evidence, workspace/target distinction and curves |
| `src/layout-settings.js`         | Catalog field schema, typed request serialization, effective limits and legacy outcome interpretation |
| `src/layout-settings.test.js`    | Control completeness, types, solver switching, SSR rendering and outcome tests |
| `src/components/flow/StageInspector.vue` | Stage execution, progress and search outcome panel |
| `src/components/flow/LayoutSettings.vue` | Primary budgets, typed solver controls, presets and advanced sections |
| `src/components/flow/SettingField.vue` | Shared typed number, checkbox, text and select control |
| `src/components/flow/LayoutOutcome.vue` | Search stop reason, workspace-only warning, retained target result and last-run settings |

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

All catalog solvers share sampled live geometry frames, including regional trials,
parallel baseline worker snapshots, tree trajectories and outline workspace growth.
Versioned frames carry a materialized layout, grid, search area, original target,
phase, work, current metrics and separately identified best metadata. The canvas
renders the selected frame's real machines, ports, logistics, support and routes;
the blue target boundary stays visible inside the amber workspace boundary.
Playback and live following use the same recorded frames. Seeking or playing never
leaves the final artifact pinned over earlier frames, and re-enabling live follows
the newest frame immediately. Expansion can enlarge and shrink the playback canvas.
Worker geometry is explicitly labeled and never spliced into a global best curve.

Frame controls: `frame_every=1` is the finest safe-boundary sampling; N samples
every N calls with an elapsed-time fallback. Zero suppresses periodic frames,
not start/expansion/construction/stop milestones. The viewer does not claim to
show individual A* steps or transient invalid repair states. Old recordings remain
readable, with unknown metrics shown as gaps rather than invented zeroes; missing
historical progress cannot be reconstructed. Area and overflow curves are separate,
and current SA trajectories are not presented as monotone best archives.

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
