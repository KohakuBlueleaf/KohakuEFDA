# KohakuEFDA

End Field Design Automation: an offline planner and layout generator for the
Automated Industry Complex (AIC) factory in Arknights: Endfield. The user gives
material supply rates, absolute output targets, a basement (the Core AIC Area:
region, id, basement level, depot level) and a mode; the tool plans recipes and
machine counts, sizes lanes, places cells, routes belts and pipes, verifies the
rules and renders the result. Nothing is injected into the game.

Design: `.internal/seed/08-design.md`. Plan: `.internal/seed/09-impl-plan.md`.
Conventions in full: `.internal/seed/06-conventions.md`. Glossary of official
EN / zh-CN / zh-TW names: `.internal/seed/04-glossary.md`. Decisions:
`.internal/seed/07-questions.md` (never edit that file; propose in chat).

**Root source for every in-game fact: `.internal/game-knowledge/`.** It is an
internal wiki that cites only external sources (extracted game tables, wikis,
cloned community tools under `.ref/`, guides, the owner's answers) and never
this project. Code, data, docs and tests take game facts from it alone and cite
the fact id (`PWR-02`, `COV-01`, …). No fact may be "unknown" or asked of the
owner in chat; research it (zh / ja / en wikis, `.ref/` repositories) and record
it there first. Never delegate that research to subagents.

## Layout

```
src/kohakuefda/          library: data/ model/ i18n/ flow/ plan/ layout/ route/ verify/ render/ cli/
src/kohakuefda-viewer/   Vue 3 viewer (JavaScript only); builds into src/kohakuefda/web_dist/
src/kohakuefda-rs/       Rust hot paths (later)
src/kohakulayout/        KohakuLayout: the netlist-to-layout framework (design in .internal/kohakulayout/)
src/kohakulayout-rs/     its native twin (pest, serde, pyo3; built with maturin into .venv)
data/<versionId>/        normalised dataset + manifest (checked in); data/raw/ is ignored
scripts/dev/             comment_budget.py and other dev tools
tests/                   flat pytest; tests/fixtures/ is test-owned data
docs/                    public docs with YAML front matter
.internal/               private notes: seed/ research, plans/ progress and goal relay
.ref/                    cloned reference repositories (ignored)
```

Imports flow one way, from `model` (the leaf; it imports nothing from the
project) through `data`, the planning and flow modules, world geometry and
occupancy, rules and the evaluator, the row template and harness, cells and
netlists, placement and routing, up to `render` and `cli`. The module-level
order is in `docs/en/dev/dependency-graph.md`; no module imports one above it.
Every subpackage has a `README.md` with a Files table and a Dependencies list;
update it when files change.

## Code rules

- Python 3.13. Modern type hints (`list[int]`, `X | None`); never `List`, `Optional`.
- No imports inside functions (only optional third-party deps, with a comment).
  Import groups: builtin, third-party, `kohakuefda`; `import` before `from`,
  shorter dotted paths first, then alphabetical.
- Rates are `fractions.Fraction` per minute; floats only in renderers.
- Registries over branching; "config is the interface": every knob a script
  reads is a module-level default it exposes.
- `logging`, never `print`, in library code. Typed exceptions per package.
- Every stochastic routine takes a `seed`; outputs are reproducible.
- Identifiers and code are English; display names come from the dataset in
  `en`, `zh-TW`, `zh-CN`.
- CLI is typer + rich; no argparse. Viewer is Vue 3 + Vite + UnoCSS +
  unplugin-vue-router, JavaScript only, no manual routes.

## Comments and docstrings

Code and comments say WHAT; WHY and HOW live in `docs/` or `.internal/`.
Inline comment only when the code cannot say it: one sentence, max 2 lines.
Docstrings: what it does, receives, returns; at most a clause naming the
algorithm; max 14 lines. Module docstrings are exempt. Escape hatch:
`# justify: <reason>` on the line above. No history, no measurements, no
memo or editorial comments. Checker: `python scripts/dev/comment_budget.py src scripts tests`.

## Tests

Flat `tests/`, lightweight, behaviour asserts over real collaborators; the only
seam is the external data source (recorded fixtures). Tests own their fixtures
under `tests/fixtures/`. No coverage gates, no file-size guard, no CI for now.

## Post-implementation tasks

1. `black .` and `ruff check .` (defaults).
2. `python scripts/dev/comment_budget.py src scripts tests`.
3. `pytest -q`.
4. For the viewer: `npm run format:check`, `npm run lint`, `npm test` and `npm run build` in `src/kohakuefda-viewer/`.
5. Update the touched subpackage READMEs and `.internal/plans/`.
6. Do not commit unless explicitly asked.

## Game-model facts that code must respect

All of them live in `.internal/game-knowledge/` with their sources; the ones
the whole design rests on: belt 30/min and pipe 120/min (LOG-01, LOG-02); a
plain belt and a plain pipe may share a cell, pipe junctions and bridges block
the belt cell (LOG-04); no side-loading, junctions only through splitters and
convergers (LOG-07); the PAC's 14 inputs and 6 outputs are depot ports and
belts enter them directly (DEP-02); pylons cover 12×12 and the PAC powers
nothing by itself (COV-01, COV-03); power is reported as the total the
machines draw (PWR-05), no generation is planned or placed;
transmuters draw 6/min of their activation fluid per built machine (ACT-03);
a Gas Dispersing Unit makes a 13×13 zone on 6/min of gas and zones do not
overlap (ENV-01, ENV-02); the Planting Unit needs no plots (PLT-04); mining is
out of scope (solids come from the depot, RES-02); targets are absolute
units/min and degrade when infeasible; only area and machine count cost;
"basement" means the Core AIC Area (REG-02, REG-04).

## KohakuLayout (`src/kohakulayout/`)

The netlist-to-layout framework built beside the project. Design set:
`.internal/kohakulayout/` (README, then pages 00 to 12; `12-impl-plan.md` holds the
milestone table). Progress: `.internal/kohakulayout/progress/` (`status.md` live per sub-step, `rounds.md` the round log); measurements: `.internal/kohakulayout/results/`. The framework
never imports the project; the project imports the framework only from milestone 13.

**The loop.** One milestone, one full loop: implement the milestone in full, all at
once, then review and audit everything at once, behaviour and cost, then the tests and
the gate, and only then measure. A bad gate starts a new loop for that milestone, never
a patch. Items inside one milestone have no priority order that lets one be skipped.

**Round end.** Every round ends with recall (the plan page for the milestone and these
rules), record (`progress/status.md` and `progress/rounds.md`: what was built, which gate
ran, what was measured, what is next) and reconcile (every divergence from the design set or rule violation
fixed now or listed with a reason). The final text block then carries:

```
## Kohaku Second Principle — Goal
- [x] M0 … - [ ] M12   (the current state of every milestone)
following kohaku first principle
```

`.claude/hooks/kl_round_end.py` blocks a stop whose last block lacks it, once;
`.claude/hooks/kl_post_edit.py` reports the file rules after every edit;
`.claude/hooks/kl_post_compact.py` points the next turn back at the plan.

**Rules on top of the project's.**

- Nested, never flat: a directory with more than about twelve siblings is a smell.
- A file is at most 600 lines (hard cap 1000); split before it grows.
- Import order, one way: `errors` → `ir` → `utils` (imports `ir` only) → `physics` →
  `state` → `flow` → `verify` → `engine` → `solvers` → `pipeline` → `service` →
  `templates` → `cli`. `scripts/dev/kl_deps.py` fails a violation, a cycle, an
  in-function import without an allowlist reason, or any `kohakuefda` import.
- No game, pack or project name inside the framework. Vocabulary lives in `kind` and
  in namespaced `attrs`; the framework never reads either.
- Fixtures are `.kl` files under `tests/kohakulayout/fixtures/`; the fast tier verifies
  them before any test reads them.
- Python is the reference. Rust is a twin behind parity tests, and every accelerated
  function falls back to Python when the module is absent or raises.
- Gates: `python scripts/dev/kl_check.py fast|unit|journey|bench|full`; every check is
  bounded and a stall is reported as STALLED, not as a failure.
- Tests have three shapes: unit (one source file, one test file), integration (one
  package, one class of complete workflows), journey (through the service). Behaviour
  asserts, real collaborators; the only seam is the process boundary.
- Shell paths are absolute; the working directory is never trusted.
