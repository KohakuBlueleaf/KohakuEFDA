# serve/

The local web application behind `kohakuefda serve` (alias `view`): the built
Studio, the artifact files of a directory, the dataset, the icons, and a JSON
API that runs a scenario stage by stage (plan, netlist, layout, verify) with
checkpoints, tunable parameters, recorded frames, a live event stream that
resumes after the last sequence seen, requirements and outcomes. `/api/solvers`
exposes the application solver catalog (`kohakuefda.solvers`); the server never
loads arbitrary Python code from HTTP settings. Catalog entries include parameter
types and parallel capability for typed controls. Invalid solver options are
rejected before a stage is queued.

Layout stage summaries retain a structured `outcome`: solver stop status, complete
routed evidence, elapsed time, work and resolved settings. A budget/step-limited
search without a routed result ends `incomplete`, preserves available diagnostics,
and does not run verification. A retained routed result ends `done`, including when
the solver status is `budget_exhausted`; execution faults remain `failed`.
Legacy partial `done` frames are reclassified on load without rewriting evidence.

## Files

| File        | Description                                                                 |
| ----------- | --------------------------------------------------------------------------- |
| `server.py` | `AppHandler` (static bundle, `/artifacts/`, `/dataset.json`, `/icons/<kind>/<id>.png`, `/api/` dispatch for GET, POST and DELETE, Server-Sent Events for `/api/runs/<id>/events`), `AppServer`, `serve()` |
| `api.py`    | `Api`: `GET /api/meta`, `/api/dataset`, `/api/examples`, `/api/params`, `/api/icons`, `/api/runs[/<id>]`, `/api/runs/<id>/artifacts/<name>`, `/api/runs/<id>/frames/<stage>`, `/api/runs/<id>/outcomes`, `/api/runs/<id>/alternatives`, `/api/runs/<id>/events?once=1`; `POST /api/runs`, `/api/runs/<id>/stages/<stage>`, `/api/runs/<id>/cancel`, `/api/requirements`, `/api/scenario/parse`, `/api/scenario/toml`; `DELETE /api/runs/<id>`; `example_scenarios()` |
| `runs.py`   | `Run` (stage states, checkpoints, frames, event log, files under `runs/<id>/`), `RunManager` (create, start a stage or a range of stages, cancel, delete, restore from the workspace, worker threads) |

## Dependencies

- `kohakuefda.model`, `kohakuefda.data`, `kohakuefda.flow`, `kohakuefda.plan`, `kohakuefda.layout`, `kohakuefda.verify`
