---
title: Frontend
summary: The Studio's architecture: stack, visual system, stores, the run API and event stream, the design entry, the stage views, the plan graph, and the canvas renderers.
tags:
  - dev
  - frontend
  - studio
  - api
---

# Frontend

`src/kohakuefda-viewer/` is a Vue 3 application in JavaScript: Vite (rolldown), UnoCSS (wind preset, attributify, carbon icons), file-based routes from `src/pages/` through unplugin-vue-router, auto-imported Vue and Pinia APIs, auto-registered components from `src/components/` and its subfolders, Pinia for state. `npm run build` writes into `src/kohakuefda/web_dist/`, which ships inside the Python package and is served by `kohakuefda serve`.

## Visual system

The theme is KohakuTerrarium's: warm neutral surfaces (`warm-50` … `warm-950`), gem accents (`iolite` primary, `aquamarine` running and done, `amber` idle and warnings, `coral` errors, `sage`, `sapphire`, `taaffeite`), Inter for text and JetBrains Mono for ids and numbers, cards with soft borders, dense chrome text. `uno.config.js` declares the colours and the shortcuts (`card`, `btn-primary`, `btn-secondary`, `btn-ghost`, `btn-icon`, `chip-<gem>`, `input-field`, `input-number`, `select-field`, `seg-group`, `panel-header`, `table-*`). `style.css` sets the fonts, the CSS variables for both themes, the scrollbar and the pulse animation. `stores/theme.js` toggles `html.dark`, persists the choice and follows the system by default. Canvases take a palette per theme from `draw.js`.

## Contract with the server

Static routes, relative to the page URL: `artifacts/index.json`, `artifacts/<file>`, `dataset.json`, `icons/<kind>/<id>.png`.

The run API (`src/kohakuefda/serve/api.py`), JSON in and out:

| Route | Body | Result |
|---|---|---|
| `GET api/meta` | | dataset version, regions, modes, stage names, basements with squares per level, hub flag and depot levels |
| `GET api/dataset` | | the dataset |
| `GET api/examples` | | bundled scenarios: name, TOML, parsed scenario |
| `GET api/params` | | default parameters per stage |
| `GET api/icons` | | the icon index: `items`, `machines`, `logistics` (id → file) and `missing` |
| `GET api/runs` | | run summaries, newest first |
| `POST api/runs` | scenario | `201`, the new run's summary |
| `GET api/runs/<id>` | | summary: stages (status, params, started, finished, error), artifact names, frame counts, `busy`, `events` |
| `GET api/runs/<id>/artifacts/<name>` | | `plan`, `netlist`, `placement`, `layout`, `evaluation` or `report` |
| `GET api/runs/<id>/frames/<stage>` | | the recorded `layout` frames |
| `GET api/runs/<id>/outcomes` | | delivered, stored, dumped, consumed and missing flows with their next products |
| `GET api/runs/<id>/alternatives` | | `alternatives`: a feasible plan per rival recipe of a used product, each with the scenario that selects it; `bannable`: machines whose ban still leaves a feasible plan |
| `GET api/runs/<id>/events?since=N` | | Server-Sent Events after sequence `N` (a `Last-Event-ID` header does the same on reconnect); `&once=1` returns them as a JSON list |
| `POST api/runs/<id>/stages/<stage>` | `{ params, through }` | `202`, the queued stages and the summary; `409` when busy or an earlier stage is not done; `400` on an unknown parameter |
| `POST api/runs/<id>/cancel` | | the summary |
| `DELETE api/runs/<id>` | | removes the run and its directory |
| `POST api/requirements` | scenario | `{ raw, intermediates }`: materials the targets need from outside, items that could be supplied instead of made |
| `POST api/scenario/parse` | `{ toml }` | `{ scenario }` |
| `POST api/scenario/toml` | scenario | `{ toml }` |

Each event is `{ seq, time, kind, stage, data }`: `kind` is `stage` (data is the stage state) or `frame` (data is the frame, with `index`, its position in the stage's frame list). The stream stays open and sends a comment every fifteen seconds while nothing happens.

## Stores

`stores/app.js` holds the dataset, the API metadata, examples, parameter defaults and the icon index; the artifacts shown by the result pages (from the served folder or from the open run); the editable scenario, the requirements it needs (refreshed with a short debounce whenever targets, region or gas change, adding every raw material to the supply as "plenty"), the outcomes of the open run; the run list, the open run's summary, its frames per stage and its stage history; the settings drafts per stage (seeded from the run's last parameters or the defaults, kept as typed until `resetDraft`); the selected stage of the Studio and whether the user pinned it. Opening a run fetches its summary, artifacts, frames and outcomes, then subscribes to its events from the summary's event count; frame events are stored at their index; stage events update the summary, clear the artifacts and frames of stages reset to idle, fetch the artifacts of stages that finish, refresh the outcomes after Plan, move the selected stage to the running one unless pinned, and raise toasts. `extend` adds a next product as a target, creates a new run and plans it. `stores/toasts.js` holds the toast queue; `api.js` wraps `fetch` and `EventSource`, reconnecting after the last sequence seen and dropping duplicates.

## Components

| Folder | Components |
|---|---|
| `chrome/` | `AppHeader` (title, dataset chip, navigation, run chip, language switch, theme toggle), `StatusBar`, `ToastCenter` |
| `common/` | `EntityIcon` (an item, machine or logistics picture with a glyph fallback), `EntityPicker` (a searchable picture grid in a modal, filtered by phase), `StatusDot`, `Metric` |
| `scenario/` | `DesignEntry` (the four steps, examples, import, export, reset, Build), `WhereStep`, `WantStep` (products with intents), `HaveStep` (materials with one rate each, intermediates already owned), `BuildStep` (simplest or efficient, advanced settings, forced recipes) |
| `flow/` | `FlowStrip`, `StageCard`, `StageInspector` (parameter drafts in groups with full ranges and choice lists, run, run to the end, stop, reset, history) |
| `views/` | `PlanView` (metrics, outcomes board, graph, other recipe paths and bannable machines, tables), `OutcomesBoard`, `NextProducts`, `NetlistView` (cell cards with fragment pictures, groups and pins), `LayoutView` (the layout stage's frames: search with the cost curve, the detailed pass with pylons, entries, wires and conflicts, the result), `VerifyView` |
| `canvas/` | `LayoutCanvas`, `FlowCanvas` (search and detail frames), `FragmentCanvas`, `Timeline`, `CostChart` |
| `tables/` | `DataTable` (with per-column cell slots), `FindingsTable`, `PlanGraph` (SVG with item pictures; nodes named by product and machine; sources named from the depot or from outside; orthogonal edges with hops at crossings and a crossing count; feedback edges under the graph; loops drawn as return arrows) |

`graph.js` lays the plan graph out the Sugiyama way: back edges found by depth-first search are cut, ranks are longest paths from the sources with every supply pulled next to its first consumer, long edges get a dummy node per intermediate column, columns are ordered by barycenter sweeps down and up, and `routeEdges` gives every edge an orthogonal polyline that leaves its node in the upper band of the node's side and arrives in the lower band, on its own track in each gap (downward edges left by descending start, upward ones by ascending, so only edges whose order flips still cross); `findCrossings` lists the crossings and `pathWithJumps` draws a hop on each; back edges leave rightwards, drop below the rows and return under the graph. `rules.js` mirrors the planner's recipe filter (region, gas, liquids, banned machines) so the product picker offers only what the planner may use. Both are pure modules with vitest tests next to them.

`composables/timeline.js` drives the timeline (index, play, speed, follow) over a frame list. `draw.js` holds the Canvas2D renderers: grid, machine footprints coloured by role with port dots and inside/outside badges, belts and pipes coloured per item with arrows (pipes dashed) and named once per wire, outside inputs as inward arrows, units with glyphs, module outlines, wire paths, overused-cell marks, and placement blocks with rotated pins; `sizeCanvas` gives every canvas a backing store at the device pixel ratio so cells stay sharp on high-density screens. It re-implements the rotation of ports and footprints (`rotateCell`, `rotateEdge`) with the same formulas as `model/geometry.py`, so what it draws matches what the verifier checks.

## Pages

`index.vue` is the Studio (design entry, flow strip, stage view, settings panel; the side panels become drawers on narrow screens); `runs.vue`, `dataset.vue`, `plan.vue`, `layout.vue`, `modules.vue`, `report.vue` are the list and result pages.

## Commands

```bash
npm install
npm run dev            # http://localhost:5173, the API must be served separately
npm run build
npm run lint
npm test               # vitest over the pure modules
npm run format:check
```
