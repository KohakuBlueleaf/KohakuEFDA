# kohakulayout.service

The run lifecycle: submit, status, events, cancel, result, best, resume. Everything a run
produces lives under `runs/<run_id>/` as self-describing IR artifacts.

| file | what |
|---|---|
| `protocol.py` | `Request`, `RunStatus`, `RunResult`, `EventFilter`, `RunState`, the `SolveService` protocol |
| `runs.py` | `RunDir`: `problem.json`, `request.json`, `status.json`, `best.layout.json`, `best.assessment.json`, `checkpoints/<seq>.json`, `events.jsonl`, the `cancel` flag; `new_run_id`, `list_runs` |
| `events.py` | `JsonlSink` (append per event, flushed), `read_events` (typed payloads back, the filter applied) |
| `local.py` | `LocalService`: the engine in the caller's process; `RunRecorder` keeps the directory current and raises `Cancelled` at the next attempt after a cancel |
| `process.py` | `ProcessService`: each run in a spawned worker running the local service's `run_now`; `wait`, `close` |

## Dependencies

`kohakulayout.errors`, `kohakulayout.ir`, `kohakulayout.engine`, `kohakulayout.pipeline`, `kohakulayout.solvers`.
