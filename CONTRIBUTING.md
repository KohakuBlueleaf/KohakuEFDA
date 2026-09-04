# Contributing

House style and the checks that enforce it. `CLAUDE.md` has the rules; this
page has the commands.

## Setup

```bash
uv venv --python 3.13            # once; the repo keeps its venv in .venv/
uv pip install -e ".[dev]"       # library + pytest, ruff, black
uv pip install -e ".[dev,cpsat,viz,native]"   # plus OR-Tools, matplotlib, maturin
```

Two parts are built separately and neither is checked in. The web app, without
which `kohakuefda serve` will not start:

```bash
cd src/kohakuefda-viewer && npm install && npm run build
```

The native routing grid, which is optional but worth about ten times the run —
the build backend is setuptools, so `pip install -e .` does not build the crate:

```bash
maturin develop --release
python -c "import kohakuefda.route.pathfinder as p; print(p.NATIVE)"   # True
```

If maturin complains that `VIRTUAL_ENV` and `CONDA_PREFIX` are both set, unset
one. If copying the extension fails with `os error 32` on Windows, a worker
process from an interrupted layout run is holding it open; stop it and rebuild.
[The native routing grid](docs/en/dev/native.md) has the detail.

## Checks

Run all of these before handing work over:

```bash
black .
ruff check .
python scripts/dev/comment_budget.py src scripts tests
pytest -q
cargo test                       # the crate's own tests
```

Viewer (`src/kohakuefda-viewer/`):

```bash
npm install
npm run format:check
npm run lint
npm test
npm run build          # writes src/kohakuefda/web_dist/
```

## Conventions in one screen

- English only in code, comments, commits and docs; translations live in
  data (`en`, `zh-TW`, `zh-CN`).
- Comments say what, never why or history; budgets are enforced by
  `comment_budget.py`.
- No imports inside functions; grouped and ordered imports.
- Flat tests that assert behaviour on real collaborators.
- One README per subpackage, kept current.
- Public docs live under `docs/<locale>/` with YAML front matter (`title`,
  `summary`, `tags`), one `# H1` per page and relative links; `tests/test_docs.py`
  checks all three and that `docs/docs.config.js` lists every English page.
  Docs describe what exists, without history.
- No commits unless asked; no CI until the project is complete.
