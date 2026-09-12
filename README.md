# KohakuLayout & KohakuEFDA

**KohakuLayout is an open framework that turns a netlist into a placed and routed layout
on a grid. KohakuEFDA is the factory planner built on it, for the Automated Industry
Complex (AIC) in *Arknights: Endfield*. This repository holds both: the framework, its
Rust twin, the planner and its web Studio.**

> Work in progress, built for fun and for learning more than for production. PRs are
> welcome.

The idea comes from how many games and tools share one problem underneath. A factory game,
a circuit schematic and a Minecraft redstone build all ask the same question: here are
machines with ports and the connections between them; where does each one stand, and where
does each wire run, under this world's rules about crossing, branching, reach and space?
Every tool that answers it rebuilds the same plumbing before its first interesting rule
runs: a grid with occupancy, placement that can be taken back, a router that knows
crossings and junctions, verification, and a search that never passes through a broken
layout.

KohakuLayout is that shared plumbing. **To lay out a new world, you write a physics pack
(what the grid means) and a synth (what you want built, as a netlist). Everything else is
reused unchanged: the IR and its text form, the transactional world, the router, the
solvers, budgets, rollback, assessment, checkpoints and the run service.** KohakuEFDA is the
first project built this way. The logic-gates pack in the tree is the second, and it is
deliberately a different world.

---

## KohakuLayout: the framework

### What the framework removes

The framework does not decide what your world allows. It removes **the layout problem
around it.** You state the rules; the framework places, routes, rolls back, checks and
searches under them. A placement and its wires are one operation, so a position that
cannot be wired never exists, and a refused step leaves the world exactly as it was.

Ownership has four categories, not two:

| | examples | may you change it |
|---|---|---|
| **Fixed protocol** | the IR levels and `.kl` text form, the refusal stages, the kernel contract, the solver protocol | No. If you change it, you are off the framework |
| **Pack hooks** | fabric, library, carriers, fields, boundaries, flow, rules, objective | Yes. That is what a pack is. Every hook has a restrictive default |
| **Override points** | the router's `TreePolicy`, a solver's `Proposals` and `Search`, passes, plugins | Optional. Subclass when your world needs its own order |
| **Yours** | what to build (planning), the synth, rendering, export to your game | Entirely |

Cells, nets and units carry a `kind` and namespaced `attrs`. The framework passes them
through and never reads them; your hooks do. That is the line between mechanism and
vocabulary.

### What ships

**The framework, `src/kohakulayout/`.**

- `ir/` holds the levels (netlist, problem, layout, assessment, refusal, frame), modules
  and macros, JSON, digests, and the `.kl` text form.
- `physics/` is the protocol with its defaults, plus shipped planners: `GreedyCover`,
  `KindCover` and `SquareSweep` for fields.
- `state/` is the world: placements, wires, units and reservations under transactions,
  the refusal chain (legal, region, overlap, port shut, route, field), the Python and
  native kernels, and the router. The router is A\* with crossings, junctions, repeaters
  and reservations, a tree router, and a lane router that lays a net lane by lane.
- `engine/`, `solvers/`, `pipeline/` and `service/` hold the context, budget, best
  archive and checkpoints; the six shipped solvers (`inorder`, `baseline`, `regional`,
  `climb`, `anneal`, `floorplan`); `solve(problem)`, the one call a project makes; and a
  run service with submit, watch, cancel and resume.
- `verify/` and `flow/` hold the rule runner and the steady-state evaluator.
- `templates/` is the extension points: a null pack, the gates pack, a skeleton solver
  and an identity plugin.

**The native twin, `src/kohakulayout-rs/`.** A Rust crate (pest, serde, PyO3) that
reproduces the text form, digests and occupancy kernel byte for byte. It runs the path
search, and whole placement attempts over a native mirror of the world. **Python is the
reference.** Every accelerated function falls back to Python when the module is absent or
declines, and parity tests hold the two to the same answers.

The split is enforced: `kohakulayout` imports nothing from `kohakuefda`, and a test that
walks every framework module fails the moment it does.

### The proof: the gates pack

Claims about frameworks are cheap, so the framework carries a second, unrelated world:
logic gates wired like a schematic. It has two carriers on two layers, jumpers where
wires cross, free branching, inputs pinned west and outputs east, and an optional power
field. There is no game in it, and every solver runs on it in the test suite.

```python
from kohakulayout.engine import Budget
from kohakulayout.pipeline import solve
from kohakulayout.templates.physics.gates import from_expressions, problem

netlist = from_expressions("""
s = a ^ b ^ cin
cout = a & b | cin & (a ^ b)
""")
result = solve(problem(netlist, width=24, height=12), solver="regional", budget=Budget(seconds=10))
print(result.outcome, result.assessment.complete)  # complete True
```

The same problem as text, from the command line:

```bash
kl solve tests/kohakulayout/fixtures/half_adder_hier.kl --solver regional --seconds 5
```

### Building your own

For a world named `NAME`, a pack module and a synth are yours, and nothing else is:

```
NAME/__init__.py    NAMEPhysics(BasePhysics): id, version, fabric(), library(), @register
     carriers.py    what may share a cell, how wires cross and branch, run limits, repeaters
     boundaries.py  where a cell may stand (anchors) and what is illegal (legal)
     fields.py      needs and emitters, only if something needs coverage
     rules.py       findings a finished layout is checked for
     synth.py       your input -> Netlist
```

**[Building your own project](docs/en/kohakulayout/custom-pack.md)** walks through the
gates pack hook by hook, then builds a fake-2D **Minecraft redstone** pack as a worked
sketch. In it, dust is a carrier with a run limit of 15 and a repeater, and an OR is two
sources on one net. Crossings go through a bridge unit on a second layer. The page says
where the sketch stops (dust joining its neighbours, facing and delay, true 3D).

---

## KohakuEFDA: the factory planner

The flagship project: an offline planner and layout generator for the AIC. You give it the
products and rates you want, what you already have coming in, and which basement (Core AIC
Area) you are building in. It plans the recipes and machine counts, sizes the belts and
pipes, places every machine, routes every lane, checks every rule the game enforces, and
hands back a layout you can build, as a text grid, a PNG or an interactive web app.

It reads static game data only. Nothing is injected into the game, and nothing is read out
of it.

Ratio calculators tell you how many machines you need. They do not tell you where to put
them. They don't say how many belts a 30/min lane feeds, which outputs stall the line
through back-pressure, whether a pylon reaches the machine you just moved, or how many
bricks your basement's depot bus actually seats. KohakuEFDA models those rules, then
solves placement and routing under them.

### Four stages

Each stage writes an artifact you can read, edit and re-enter:

| stage | decides |
|---|---|
| **plan** | which recipes, how many of each machine, what rate every lane carries |
| **netlist** | machines as cells with pins, and the nets that join them |
| **layout** | where every machine stands and where every belt and pipe runs, on KohakuLayout |
| **verify** | the geometry rules, and the steady state the line settles at |

### The Endfield pack

`src/kohakuefda/physics/` is the game as a KohakuLayout pack. It covers:
- belts at 30/min and pipes at 120/min (`LOG-01`, `LOG-02`), which may share a cell,
  with bridges where two belts cross (`LOG-04`);
- junctions only through splitters and convergers (`LOG-07`);
- the PAC's depot ports fed directly (`DEP-02`), and the depot bus with its bricks;
- pylons reaching 12×12, laid afresh after every placement (`COV-01`);
- gas zones that never overlap (`ENV-01`, `ENV-02`).

Every in-game fact is recorded with its source in `.internal/game-knowledge/` and cited
by its id in the code and docs. The project's router, solver and anchor ranking sit on
the framework's override points; none of them live in the framework.

### Status

**Working.** The whole pipeline, from scenario to verified layout, through the CLI and
the Studio. The layout stage reproduces the engine it replaced operation for operation:
first trials and replayed later trials match its lanes, units and pylons exactly. On the
two dense benchmark cases its first trial runs 2 to 18 percent faster than that engine,
measured in the same hour.

**In progress.** The dense cases, 60 to 130 machines, do not yet complete reliably within
a two-minute budget. The current work is the search's later trials.

---

## Quickstart

Python 3.13 or newer, on Windows, macOS or Linux.

```bash
uv venv --python 3.13
uv pip install -e .              # the framework, the planner and both CLIs
uv pip install -e ".[viz]"       # + matplotlib, for PNG output
uv pip install -e ".[dev]"       # + pytest, ruff, black
```

Two parts are **built separately**, and neither is checked into the repository.

**The native twin (optional, several times faster).** The package's build backend is
setuptools, so `pip install -e .` does *not* build the crate. Use maturin from the crate:

```bash
uv pip install -e ".[native]"                          # installs maturin
cd src/kohakulayout-rs && maturin develop --release    # builds kohakulayout_rs into the venv
python -c "import kohakulayout_rs; print('ok')"
```

If maturin says **`Both VIRTUAL_ENV and CONDA_PREFIX are set`**, it is refusing to guess.
Unset one (`unset CONDA_PREFIX`) and run it again. Without the twin, the Python kernel
runs and gives the same layouts.

**The Studio web app.** `kohakuefda serve` refuses to start without it:

```bash
cd src/kohakuefda-viewer
npm install
npm run build                    # writes src/kohakuefda/web_dist/
```

Then lay out a bundled scenario and open it. A normalised dataset for one game version
ships in `data/`, so this works offline straight from a clone:

```bash
kohakuefda layout tests/fixtures/scenario_valley_battery.toml -o out/
kohakuefda render out/layout.json
kohakuefda serve  out/ --open
```

Every command:

```bash
kohakuefda plan     scenario.toml          # recipes, machine counts, lanes, stability
kohakuefda netlist  scenario.toml          # the cells and the nets between their pins
kohakuefda layout   scenario.toml -o out/  # the whole pipeline; writes every artifact
kohakuefda check    out/layout.json        # rules and steady-state rates for any layout
kohakuefda render   out/layout.json --png  # text grid, or a picture
kohakuefda serve    out/ --open            # the Studio: design, run, watch, tune, rerun
kohakuefda data     fetch                  # rebuild the dataset from the pinned tables
kohakuefda glossary items                  # the trilingual name table

kl verify | json | text | pretty | flatten | diff    # the framework's IR tools
kl route | assess | solve | runs                     # route, assess and solve any pack
```

## Development

```bash
black . && ruff check .
python scripts/dev/comment_budget.py src scripts tests
pytest -q
python scripts/dev/kl_check.py fast | unit | bench   # the framework's gates
cd src/kohakuefda-viewer && npm run lint && npm test && npm run build
```

`CONTRIBUTING.md` has the full check suite; `CLAUDE.md` has the house rules.

## Documentation

**[`docs/`](docs/en/README.md)** is written to be read, in `en`, with `zh-TW` and `zh-CN`
landing pages.

| | |
|---|---|
| [KohakuLayout](docs/en/kohakulayout/README.md) | the framework: IR, physics packs, the world and router, engine, solvers, service, conformance |
| [Building your own project](docs/en/kohakulayout/custom-pack.md) | a new pack step by step: logic gates, and a fake-2D Minecraft redstone sketch |
| [Getting started](docs/en/guides/getting-started.md) · [tutorials](docs/en/tutorials/README.md) | a first plan and a first layout with KohakuEFDA |
| [Concepts](docs/en/concepts/README.md) | the factory model, planning, cells and netlists, placement and routing, verification |
| [Reference](docs/en/reference/README.md) | the CLI, the scenario file, the artifacts, the rules |
| [Development](docs/en/dev/README.md) | internals, [the native twin](docs/en/dev/kohakulayout-twin.md), the [dependency graph](docs/en/dev/dependency-graph.md), testing |

## Repository

```
   src/kohakulayout/        the framework: ir, physics, state (world, kernels, router),
                            engine, solvers, pipeline, service, verify, flow, templates
   src/kohakulayout-rs/     its native twin (Rust, PyO3; optional)
   src/kohakuefda/          the planner: data, plan, flow, synth, the Endfield physics
                            pack, layout, verify, render, cli
   src/kohakuefda-viewer/   the Studio web app (Vue 3, JavaScript)
   data/<versionId>/        the normalised dataset and its manifest, per game hotfix
   docs/                    public documentation
   tests/                   the project suite; tests/kohakulayout/ is the framework's
   scripts/dev/             the gates: kl_check, kl_deps, comment_budget
```

## Licence

Apache-2.0. Game data, names and mechanics belong to Hypergryph / Gryphline. This project
ships only normalised numbers and identifiers derived from community data sources, and is
not affiliated with the game's publisher. Minecraft is a trademark of Mojang Studios; the
redstone sketch in the docs is an illustration and not affiliated with it.
