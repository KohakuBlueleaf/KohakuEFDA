# KohakuLayout & KohakuEFDA

**KohakuLayout is a framework that turns a netlist into a placed and routed layout on a
grid, so you stop rebuilding placement and routing every time a new world needs a layout.
KohakuEFDA is the factory planner built on it, for the Automated Industry Complex (AIC) in
*Arknights: Endfield*. This repository holds both: the framework, its Rust twin, the
planner and its web Studio.**

> Work in progress, built for fun and for learning more than for production. PRs are
> welcome.

---

## See it run (60 seconds)

```bash
uv venv --python 3.13 && uv pip install -e .
kl solve tests/kohakulayout/fixtures/half_adder_hier.kl --solver regional --seconds 5
kohakuefda layout tests/fixtures/scenario_valley_battery.toml -o out/ && kohakuefda render out/layout.json
```

The first command lays out a half adder in the framework's text form; the second plans a
battery line in Endfield and lays it out. The same framework run, as a library:

```python
from kohakulayout.engine import Budget
from kohakulayout.pipeline import solve
from kohakulayout.templates.physics.gates import from_expressions, problem

netlist = from_expressions("""
s = a ^ b ^ cin
cout = a & b | cin & (a ^ b)
""")
result = solve(problem(netlist, width=24, height=12), solver="regional", budget=Budget(seconds=10))
print(result.outcome, result.assessment.complete)   # complete True
print(result.layout.placements, result.layout.wires)
```

Want the planner? [Getting started](docs/en/guides/getting-started.md). Want your own world
on the framework? [Building your own project](docs/en/kohakulayout/custom-pack.md).

## What this is

A factory game, a circuit schematic and a Minecraft redstone build share one problem
underneath: here are machines with ports and the connections between them; where does
each one stand, and where does each wire run, under this world's rules about crossing,
branching, reach and space? Every tool that answers it rebuilds the same plumbing before
its first interesting rule runs: an occupancy grid, placement that can be taken back, a
router that knows crossings and junctions, verification, and a search that never passes
through a broken layout.

KohakuLayout is that plumbing in one place. **To lay out a new world you write a physics
pack (what the grid means) and a synth (what you want built, as a netlist). The IR and its
text form, the transactional world, the router, the solvers, budgets, rollback,
assessment, checkpoints and the run service are reused unchanged.** KohakuEFDA is the
first project built this way; the logic-gates pack in the tree is the second, and it is
deliberately a different world.

| | what to build | where it goes | what you see |
|---|---|---|---|
| **the question** | recipes and rates, or a truth table | placements and wires on a grid | a picture, a blueprint, a schematic |
| **who answers** | your planner (KohakuEFDA's `plan`) | **KohakuLayout** | your renderer (KohakuEFDA's `render`, the Studio) |

## Is this for you?

**You probably want KohakuLayout if** your world is a grid with layers, your parts have
ports on their sides, your connections have rules (who may share a cell, how wires cross
and branch, how far a run may go), and you want placement and routing without writing
the search.

**You probably don't if** your geometry is continuous rather than a grid, your circuits
need timing or analog behaviour checked (the flow evaluator settles steady-state rates,
it is not a logic or SPICE simulator), or you need a layout in milliseconds.

---

## KohakuLayout: the architecture

### The IR, level by level

Every stage reads one level and writes the next. Each level is a pydantic model with a
structural `check()`, canonical JSON, a text form and a digest.

```text
 your input  ──synth──▶  Netlist (L3)  ─────────┐
                         cells, pins, nets,     │
                         groups, modules        ├──▶  Problem  ──▶  pipeline.solve  ──▶  Layout (L2)  ──▶  Assessment (L1)
                                                │     physics ref,   passes, then a      placements,       metrics, the pack's
 physics pack ──fabric(params)──▶ Fabric ───────┘     fabric,        solver on an        wires, units,     terms, findings,
                                  grid, layers,       netlist,       engine context      reservations      complete, valid
                                  carriers, regions   params

 every refused step on the way  ──▶  Refusal (stage, subject, detail)
 progress on the way            ──▶  Frame (a snapshot for a viewer)
```

| level | class | holds |
|---|---|---|
| L3 | `Netlist` | a footprint library, cells with pins and constraints, nets with sources and sinks, groups, modules and macros |
| — | `Problem` | a physics id, a `Fabric` (size, layers, carriers, regions, entries), a netlist, parameters |
| L2 | `Layout` | placements (cell, x, y, rotation), macro instances, wires as cell segments per layer, units, reservations |
| L1 | `Assessment` | the framework metrics, the pack's terms, findings, `complete` and `valid` |
| — | `Refusal`, `Frame` | why an attempt was refused, as a stage of the placement chain; a snapshot of a run |

Rates are `Fraction`s, never floats. Hierarchy is supported, never enforced: a module is
a netlist with ports, a macro a module with a layout fragment, and the digest is always
taken on the flat form. Any level can be written in the `.kl` line language beside JSON,
byte for byte round-trippable:

```text
kl 1
physics gates@1
fabric 24x12 layers=ground,overhead entries=W,E
carrier wire ground
lib AND 3x3 { a in wire W0 ; b in wire W2 ; y out wire E1 }
lib IN  1x1 { y out wire E0 }
lib OUT 1x1 { a in wire W0 }
cell a  IN  at=edge side=W
cell b  IN  at=edge side=W
cell g1 AND
cell y  OUT at=edge side=E
net n1 wire : a.y -> g1.a
net n2 wire : b.y -> g1.b
net n3 wire : g1.y -> y.a
```

### Runtime hierarchy

```text
Your project / the kl CLI / your UI
        |
        v
+----------------------+     optional: in-process or one worker per run
| Service              |  submit, status, events, cancel, resume;
|                      |  a self-describing run directory per run
+----------------------+
        |
        v
+----------------------+     the one call a project makes
| pipeline.solve       |  passes over the problem (verified after each),
|                      |  then a solver on a fresh context
+----------------------+
        |
        v
+----------------------+     owns no search
| Engine (Context)     |  budget, the seeded rng, attempts, the best archive,
|                      |  frames, plugins, checkpoints, workspaces
+----------------------+
        |  runs
        v
+----------------------+     a strategy; never reads a kind or a rule
| Solver               |  construct, then improve; sees structure, anchors,
|                      |  refusals and assessments
+----------------------+
        |  acts only through
        v
+----------------------+     one budget unit per mutation
| Builder              |  place, withdraw, route, reserve, admits, marks
+----------------------+
        |
        v
+----------------------+     every mutation journaled; a refusal rolls back
| World                |  placements, wires, units, reservations; the placement
|                      |  chain, the router, the cover planner
+----------------------+
        |
        v
+----------------------+     byte-exact save and load
| Kernel               |  per-layer occupancy, each wire's run per cell;
|                      |  PyKernel, or the native Grid from the Rust twin
+----------------------+

 The physics pack sits beside every box: the world, the router, the verify runner and
 the flow evaluator ask its hooks. Nothing in the framework reads its vocabulary.
```

- **Service** is the run lifecycle. `LocalService` runs in the caller's process,
  `ProcessService` spawns a worker; a project calls the protocol and never learns which.
- **Engine** gives a solver everything a search needs: `attempt(fn)` runs a step inside a
  transaction, `snapshot`/`restore` take the whole state as a token, `consider`/`accept`
  keep the best (valid, then complete, then fewest gaps, then the objective), and
  plugins add policy at hooks (budget accounting, frame sampling, screens, dedup).
- **Solvers** are registered by id: `inorder`, `baseline`, `regional`, `climb`,
  `anneal`, `floorplan`. A project's construction plugs in as a subclass through
  `Proposals` (how anchors are ranked) and `Search` (which cell goes next).
- **World** is the only thing that changes state, and only inside a transaction, so a
  refused step leaves the digest exactly as it was.

### One placement, and which hook answers each step

Placing a cell and routing its wires are one operation, so a position that cannot be
wired never exists.

```text
builder.place(cell, x, y, rot)                                   pack hooks consulted
   |
   |-- inspect ......... rotation, region, overlap, ports kept    boundaries, carriers.may_share
   |                     open; what the footprint may displace
   |-- write ........... trim or unroute the wires under it,
   |                     lift displaced emitters, occupy, table
   |                     the cell's pins
   |-- legal ........... the pack's own refusal                  boundaries.legal
   |-- route ........... the nets the cell made ready or grew:    router policy (lanes, order),
   |                     lanes in order, A* per lane, then the    carriers.crossing / junction /
   |                     crossing, junction and repeater units    run_limit / repeater,
   |                                                              boundaries.unit_region
   |-- field ........... emitters for the cell's needs, swept     fields.needs / cover / sweep
   |                     kinds laid afresh
   `-- accept, or refuse with (stage, subject, detail) and roll every write back;
       physics.diagnose picks the refusal reported
```

The router is a slot. The shipped occupants are a negotiated-congestion tree router and
a lane router that lays each net lane by lane in a policy's order (`TreePolicy`: which
lanes, in what order, where a lane may start and end). A* runs on one layer over the
kernel, where another net's wire is a crossing when the pack allows one and the other
wire runs straight across, shareable when the carriers say so, and otherwise a wall.

### The physics pack

A pack is a class with an `id` and a `version`, registered by name (`gates@1`). Every hook
has a default in `BasePhysics`, and each default is the most restrictive answer, so a pack
relaxes exactly what its world allows.

| hook | the pack states | default |
|---|---|---|
| `fabric(params)` | grid size, layers, carriers and their layers, regions, entry sides | required |
| `library()` | footprints with ports (side, offset, direction, carrier) | required |
| `carriers` | `may_share`, `crossing` (forbidden, free, or through a unit), `junction`, `run_limit`, `repeater` | exclusive cells, no crossings or junctions |
| `fields` | `needs(cell)`, emitters and their reach, `cover`, `sweep` | no fields |
| `boundaries` | `anchors`, `legal`, `outside`, `crossing_region`, `unit_region`, `anchor_rows` | anywhere in `build` |
| `flow` | split and merge, and the routed evaluator's hooks | even split, capped merge |
| `rules`, `objective` | the verify deck; the weights of "better" | none; area and units |

Cells, nets and units carry a `kind` and `attrs` under the pack's namespace. The
framework passes them through and never reads them; the pack's hooks do. That is the
line between mechanism and vocabulary.

### The native twin

`src/kohakulayout-rs/` reproduces the text form, digests and occupancy kernel byte for
byte, runs the path search, and answers whole placement attempts, admission checks and
routing passes over a mirror of the world. **Python is the reference**: every accelerated
call falls back to Python when the module is absent or declines, and parity tests hold
the two to the same answers.

```text
          Python world (the reference)                        kohakulayout_rs (optional)
 +-----------------------------------------+   statics once  +--------------------------------+
 | World.place / World.admits /            | --------------> | records: the mirror            |
 |   the lane router's routing pass        |  sync per call  |   (what changed since the last)|
 |   ask the twin first                    |                 | a simulated world + undo log:  |
 |                                         | <-------------- |   inspect, lay, A*, commit,    |
 | a refusal comes back as Python's;       |     answer      |   fields; every write undone   |
 | placed or declined, Python places it    |                 |                                |
 +-----------------------------------------+                 +--------------------------------+
```

### Ownership

| | examples | may you change it |
|---|---|---|
| **Fixed protocol** | the IR levels and `.kl` form, the refusal stages, the kernel contract, the solver protocol | No. If you change it, you are off the framework |
| **Pack hooks** | fabric, library, carriers, fields, boundaries, flow, rules, objective | Yes. That is what a pack is |
| **Override points** | the router's `TreePolicy` and `order`, a solver's `Proposals` and `Search`, passes, plugins | Optional. Subclass when your world needs its own order |
| **Yours** | what to build, the synth, rendering, export to your game | Entirely |

Imports run one way, and `kohakulayout` imports nothing from any project; a test that
walks every framework module fails the moment it does:

```text
errors -> ir -> utils (ir only)
            -> physics -> state -> flow -> verify -> engine -> solvers -> pipeline -> service
templates may import anything below them; cli is the top.
```

### The proof: the gates pack

`src/kohakulayout/templates/physics/gates/` is a second, unrelated world: logic gates on
two layers, jumpers where wires cross, free branching, inputs pinned west and outputs east,
and an optional power field. It has no game in it, and every solver runs on it in the test
suite. [Building your own project](docs/en/kohakulayout/custom-pack.md) walks through it
hook by hook, then builds a fake-2D **Minecraft redstone** pack as a worked sketch: dust as
a carrier with a run limit of 15 and a repeater, an OR as two sources on one net, crossings
through a bridge unit on a second layer.

---

## KohakuEFDA: the factory planner

The flagship project: an offline planner and layout generator for the AIC. You give it the
products and rates you want, what you already have coming in, and which basement (Core AIC
Area) you build in. It plans the recipes and machine counts, sizes the belts and pipes,
places every machine, routes every lane, checks every rule the game enforces, and hands
back a layout you can build. It reads static game data only; nothing is injected into the
game or read out of it.

### The pipeline

Four stages, each writing an artifact you can read, edit and re-enter. The layout and
verify stages run on KohakuLayout through the synth, which translates both ways.

```text
scenario.toml --plan--> plan.json --netlist--> netlist.json
   recipes, machine        one cell per machine, pins per lane,
   counts, lane rates      bricks, zones, one net per item
                                               |
         +------------------- layout stage ----+-------------------------------------+
         |  synth.problem_of   project netlist -> KohakuLayout Problem (Endfield pack) |
         |  pipeline.solve     EndfieldRouter, endfield.regional / climb / anneal     |
         |  synth.layout_of    framework Layout -> the project's placement and layout |
         +---------------------------------------+-----------------------------------+
                                                 v
                          placement.json, layout.json, frames for the Studio
                                                 |
         +------------------- verify stage ------+-----------------------------------+
         |  synth.reverse      any project layout -> framework problem and layout     |
         |  verify runner      kl.* and endfield.* rules                              |
         |  routed evaluator   steady-state rates under the pack's flow hooks         |
         +---------------------------------------+-----------------------------------+
                                                 v
                                   evaluation.json, report.json
```

Because verify reads a layout back from its geometry alone, any layout can be checked,
not only the ones the planner made.

### Where the project plugs into the framework

| framework slot | KohakuEFDA's occupant | lives in |
|---|---|---|
| physics pack | the Core AIC Area and its ring; belts at 30/min and pipes at 120/min (`LOG-01`, `LOG-02`) sharing a cell, bridges where belts cross (`LOG-04`); junctions through splitters and convergers (`LOG-07`); pylons reaching 12×12, laid afresh by `PylonSweep` (`COV-01`); the depot bus and its bricks; gas zones (`ENV-01`, `ENV-02`); the flow hooks and the rules deck | `physics/` |
| router policy and order | `LanePolicy` (lanes laid pipes first, then role, rate and span) and `EndfieldRouter` | `layout/router.py` |
| solver construction | `EndfieldProposals` and `EndfieldSearch` under `endfield.regional`, `endfield.climb`, `endfield.anneal` | `solvers/` |
| synth | `problem_of`, `layout_of`, `reverse`, the frame observer | `synth/` |
| run service and frames | the Studio's live runs, frames and replays | `serve/`, `synth/frames.py` |

Every in-game fact is cited by id (`LOG-01`, `COV-02`, `DEP-18`, …) from the maintainers'
knowledge base, which records each with its source.

```text
cli / serve
     |
layout stages ---------------------------------> kohakulayout
     |                                              ^      ^
verify ---> synth ---> physics (the pack) ----------+      |
             |            solvers (on the protocol) -------+
             v
   layout/board, settings, router      plan (recipes, MILP, machines, netlist)
             \                            /
              flow (lanes, stability, the evaluation schema)
                         |
                       model (domain records, footprints, the layout schema)
```

### Status

**Working.** The whole pipeline, from scenario to verified layout, through the CLI and
the Studio. The layout stage reproduces the engine it replaced operation for operation:
first trials and replayed later trials match its lanes, units and pylons exactly, and its
first trial runs 2 to 18 percent faster than that engine on the two dense benchmark
cases, measured in the same hour.

**In progress.** Dense cases of 60 to 130 machines do not yet complete reliably within a
two-minute budget; the current work is the search's later trials.

---

## Quick start

Python 3.13 or newer, on Windows, macOS or Linux.

```bash
uv venv --python 3.13
uv pip install -e .              # both packages and both CLIs (kl, kohakuefda)
uv pip install -e ".[viz]"       # + matplotlib, for PNG output
uv pip install -e ".[dev]"       # + pytest, ruff, black
```

**The native twin (optional, several times faster).** The build backend is setuptools,
so `pip install -e .` does not build the crate. Use maturin at the repository root, where
the crate's `Cargo.toml` sits beside `pyproject.toml`:

```bash
uv pip install -e ".[native]"                          # installs maturin (rustc 1.88 or newer)
maturin develop --release                              # builds kohakulayout_rs into the venv
python -c "import kohakulayout_rs; print('ok')"
```

If maturin says **`Both VIRTUAL_ENV and CONDA_PREFIX are set`**, unset one
(`unset CONDA_PREFIX`) and run it again. Without the twin the Python kernel runs and gives
the same layouts.

**The Studio web app.** `kohakuefda serve` refuses to start without it:

```bash
cd src/kohakuefda-viewer && npm install && npm run build   # writes src/kohakuefda/web_dist/
kohakuefda serve out/ --open
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

## Codebase map

```text
src/kohakulayout/            the framework
  ir/                        the levels, modules and macros, JSON, digests, the .kl text form
  physics/                   the pack protocol, BasePhysics and every default, the registry,
                             cover planners (GreedyCover, KindCover, SquareSweep)
  state/                     the World and its placement chain, transactions, snapshots,
    kernel/                  occupancy kernels: PyKernel, the native Grid, the recording kernel
    router/                  tree and lane routers, A*, crossing/junction/repeater units,
                             reservations, the native mirror (native_route.py)
  flow/                      the steady-state evaluators (fixedpoint, routed)
  verify/                    the rule runner and the structural rules
  engine/                    Context, Builder, Budget, the best archive, plugins, checkpoints
  solvers/                   the protocol, registries, inorder, baseline, regional, local
                             (climb, anneal), structural (floorplan), level-3 conformance
  pipeline/                  passes and solve(problem)
  service/                   local and process services, run directories, events
  utils/                     netlist builders and passes; on no framework path
  templates/                 the null and gates packs, the skeleton solver, a plugin
  cli/                       the kl command
src/kohakulayout-rs/         the native twin (Rust, PyO3): text form, kernel, search, attempts
src/kohakuefda/              the planner
  data/ model/ i18n/         the dataset, domain records, trilingual names
  flow/ plan/                lanes and stability; recipes, the MILP planner, the netlist
  physics/                   the Endfield pack
  synth/                     project <-> framework translation, both ways, and frames
  solvers/ layout/           the project's solvers; the board, stages, settings, router
  verify/ render/            the checks and the report; text, PNG, the viewer bundle
  serve/ cli/                the Studio's server; the kohakuefda command
src/kohakuefda-viewer/       the Studio web app (Vue 3, JavaScript)
data/<versionId>/            the normalised dataset and its manifest, per game hotfix
docs/                        tutorials, guides, concepts, reference, development
tests/                       the project suite; tests/kohakulayout/ is the framework's
scripts/dev/                 the gates: kl_check, kl_deps, comment_budget
```

Every subpackage has its own README with its files and dependency direction.

## Documentation map

Full docs live in [`docs/`](docs/en/README.md), in `en` with `zh-TW` and `zh-CN` landing
pages.

| | |
|---|---|
| [KohakuLayout](docs/en/kohakulayout/README.md) | the framework's contracts, page by page |
| [the IR and its text form](docs/en/kohakulayout/ir.md) · [physics packs](docs/en/kohakulayout/physics.md) · [the world and the router](docs/en/kohakulayout/state.md) | levels and `.kl`; every hook and default; the placement chain, routing, kernels |
| [the engine](docs/en/kohakulayout/engine.md) · [solvers](docs/en/kohakulayout/solvers.md) · [the service](docs/en/kohakulayout/service.md) · [conformance](docs/en/kohakulayout/conformance.md) | context and builder; the shipped families; runs; the levels of proof |
| [Building your own project](docs/en/kohakulayout/custom-pack.md) | a new pack step by step: logic gates, and a fake-2D Minecraft redstone sketch |
| [Getting started](docs/en/guides/getting-started.md) · [tutorials](docs/en/tutorials/README.md) | a first plan and a first layout with KohakuEFDA |
| [The pipeline](docs/en/concepts/foundations/the-pipeline.md) · [concepts](docs/en/concepts/README.md) | the four stages and their artifacts; the factory model, planning, layout, verification |
| [Reference](docs/en/reference/README.md) | the CLI, the scenario file, the artifacts, the rules |
| [Development](docs/en/dev/README.md) | [dependency graph](docs/en/dev/dependency-graph.md), [the native twin](docs/en/dev/kohakulayout-twin.md), internals, testing |

## Development

```bash
black . && ruff check .
python scripts/dev/comment_budget.py src scripts tests
pytest -q
python scripts/dev/kl_check.py fast | unit | bench   # the framework's gates
cd src/kohakuefda-viewer && npm run lint && npm test && npm run build
```

`CONTRIBUTING.md` has the full check suite; `CLAUDE.md` has the house rules.

## FAQ

**Does KohakuEFDA touch the game?** No. It reads a normalised dataset built from
community data tables and writes layouts you build yourself.

**Do I need Rust?** No. The twin is optional and gives the same layouts; it is faster.

**Can I use KohakuLayout for my own game or tool?** Yes, that is what it is for. Write a
pack and a synth; [Building your own project](docs/en/kohakulayout/custom-pack.md) shows
how, on logic gates and on redstone.

**Is a run reproducible?** Yes, for the same seed, solver, settings and budget in work
units. A budget in seconds may stop at a different step under a different load.

**Why is a refusal a value, not an exception?** A search is made of refused attempts.
Each carries the stage that refused it, so a solver can learn from it and the world can
prove it rolled back.

## Licence

Apache-2.0. Game data, names and mechanics belong to Hypergryph / Gryphline. This project
ships only normalised numbers and identifiers derived from community data sources, and is
not affiliated with the game's publisher. Minecraft is a trademark of Mojang Studios; the
redstone sketch in the docs is an illustration and not affiliated with it.
