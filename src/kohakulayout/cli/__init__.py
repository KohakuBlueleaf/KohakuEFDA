"""``kl``: the dev commands over IR files, so any tool can own any level."""

import json
from pathlib import Path
from typing import Annotated

import typer

from kohakulayout.cli.io import levels_from_file, load_all, pick, present, write_out
from kohakulayout.engine import Budget, Context
from kohakulayout.errors import KohakuLayoutError
from kohakulayout.ir import Layout, Netlist, Problem, write
from kohakulayout.ir.dump import dump
from kohakulayout.ir.json import pretty as pretty_json
from kohakulayout.physics import get as get_physics
from kohakulayout.pipeline import solve as run_solve
from kohakulayout.service import LocalService, Request, list_runs
from kohakulayout.state import World, make_router
from kohakulayout.templates import GatesPhysics, GatesPowerPhysics, NullPhysics
from kohakulayout.verify import report

app = typer.Typer(
    help="KohakuLayout dev commands over IR files (.kl text or .json).",
    no_args_is_help=True,
)

FilesArg = Annotated[
    list[Path],
    typer.Argument(
        exists=True, dir_okay=False, help="IR files; later files see earlier ones"
    ),
]
OutOpt = Annotated[
    Path | None, typer.Option("--out", "-o", help="write here instead of stdout")
]
LevelOpt = Annotated[
    str | None, typer.Option("--level", help="problem | netlist | layout | assessment")
]


def _fail(message: str) -> None:
    typer.echo(message, err=True)
    raise typer.Exit(code=1)


@app.command()
def verify(files: FilesArg) -> None:
    """Parse every file, verify every level it holds, print the problems."""
    bad = 0
    for path in files:
        try:
            levels = levels_from_file(path)
        except KohakuLayoutError as exc:
            typer.echo(f"{path}: {exc}")
            bad += 1
            continue
        for level in present(levels):
            problems = level.check()
            if (
                isinstance(level, Layout)
                and levels.netlist is not None
                and levels.fabric is not None
            ):
                problems += level.check_against(levels.netlist, levels.fabric)
            for line in problems:
                typer.echo(f"{path}: {level.level}: {line}")
            bad += bool(problems)
            typer.echo(
                f"{path}: {level.level}: {'ok' if not problems else f'{len(problems)} problem(s)'} digest {level.digest()[:12]}"
            )
    if bad:
        raise typer.Exit(code=1)


@app.command("json")
def to_json(files: FilesArg, out: OutOpt = None, level: LevelOpt = None) -> None:
    """Text to canonical JSON."""
    try:
        chosen = pick(load_all(files), level)
    except KohakuLayoutError as exc:
        _fail(str(exc))
    write_out(chosen.to_json() + "\n", out)


@app.command()
def text(files: FilesArg, out: OutOpt = None, level: LevelOpt = None) -> None:
    """JSON (or text) to canonical text; a layout gets pin endpoints when its problem is given too."""
    try:
        levels = load_all(files)
        chosen = pick(levels, level)
    except KohakuLayoutError as exc:
        _fail(str(exc))
    write_out(write(chosen, levels.problem), out)


@app.command()
def pretty(files: FilesArg, level: LevelOpt = None) -> None:
    """The picture of a layout, or a readable dump of any other level."""
    try:
        levels = load_all(files)
        chosen = pick(levels, level)
    except KohakuLayoutError as exc:
        _fail(str(exc))
    if isinstance(chosen, Layout):
        typer.echo(dump(chosen, levels.netlist, levels.fabric), nl=False)
    else:
        typer.echo(pretty_json(chosen))


@app.command()
def flatten(files: FilesArg, out: OutOpt = None, level: LevelOpt = None) -> None:
    """Expand modules, macros and instances; ids joined with a slash."""
    try:
        levels = load_all(files)
        chosen = pick(levels, level)
    except KohakuLayoutError as exc:
        _fail(str(exc))
    if isinstance(chosen, Problem):
        flat = chosen.model_copy(update={"netlist": chosen.netlist.flatten()})
    elif isinstance(chosen, Netlist):
        flat = chosen.flatten()
    elif isinstance(chosen, Layout):
        if levels.netlist is None:
            _fail("flattening a layout needs its problem or netlist")
        flat = chosen.flatten(levels.netlist)
    else:
        flat = chosen
    write_out(write(flat, levels.problem), out)


@app.command()
def diff(first: Path, second: Path) -> None:
    """A content diff of two levels, digest aware: exits 1 when they differ."""
    try:
        a = pick(levels_from_file(first), None)
        b = pick(levels_from_file(second), None)
    except KohakuLayoutError as exc:
        _fail(str(exc))
    if a.digest() == b.digest():
        typer.echo(f"identical: {a.level} {a.digest()[:12]}")
        return
    ca, cb = a.canonical(), b.canonical()
    for key in sorted(set(ca) | set(cb)):
        if ca.get(key) != cb.get(key):
            typer.echo(f"{key}: {json.dumps(ca.get(key), sort_keys=True)[:120]}")
            typer.echo(
                f"{' ' * len(key)}  {json.dumps(cb.get(key), sort_keys=True)[:120]}"
            )
    raise typer.Exit(code=1)


RouterOpt = Annotated[
    str, typer.Option("--router", help="router id; default is the shipped one")
]

SHIPPED = (GatesPhysics, GatesPowerPhysics, NullPhysics)


@app.command()
def route(files: FilesArg, out: OutOpt = None, router: RouterOpt = "default") -> None:
    """Route every unrouted net of a placed layout; writes the layout, exits 1 on a refusal."""
    try:
        levels = load_all(files)
        if levels.problem is None or levels.layout is None:
            _fail("routing needs a problem and a layout")
        world = World(
            levels.problem,
            get_physics(levels.problem.physics),
            router=make_router(router),
        )
        world.load(levels.layout)
        refusals = []
        with world.transaction() as tx:
            for net in world.unrouted():
                refusal = world.route(net.id)
                if refusal is not None:
                    refusals.append(refusal)
            tx.commit()
    except KohakuLayoutError as exc:
        _fail(str(exc))
    write_out(write(world.freeze(), levels.problem), out)
    for refusal in refusals:
        typer.echo(f"{refusal.subject}: {refusal.stage}: {refusal.detail}", err=True)
    if refusals:
        raise typer.Exit(code=1)


RootOpt = Annotated[
    Path | None,
    typer.Option(
        "--root", help="record the run under this directory through the service"
    ),
]
SolverOpt = Annotated[str, typer.Option("--solver", help="solver id")]
SeedOpt = Annotated[int, typer.Option("--seed", help="the run's seed")]
UnitsOpt = Annotated[int | None, typer.Option("--units", help="budget in units")]
SecondsOpt = Annotated[
    float | None, typer.Option("--seconds", help="budget in seconds")
]
ParamOpt = Annotated[
    list[str] | None, typer.Option("--param", "-p", help="solver parameter key=value")
]


@app.command()
def assess(files: FilesArg, out: OutOpt = None) -> None:
    """Assess a layout against its problem; writes the assessment, exits 1 when it is not valid."""
    try:
        levels = load_all(files)
        if levels.problem is None or levels.layout is None:
            _fail("assessing needs a problem and a layout")
        ctx = Context(levels.problem, router=None)
        ctx.world.load(levels.layout)
        assessment = ctx.assess()
    except KohakuLayoutError as exc:
        _fail(str(exc))
    write_out(write(assessment, levels.problem), out)
    typer.echo(report(assessment), err=True)
    if not assessment.valid:
        raise typer.Exit(code=1)


@app.command()
def solve(
    files: FilesArg,
    out: OutOpt = None,
    solver: SolverOpt = "inorder",
    seed: SeedOpt = 0,
    units: UnitsOpt = None,
    seconds: SecondsOpt = None,
    param: ParamOpt = None,
    router: RouterOpt = "default",
    root: RootOpt = None,
) -> None:
    """Solve a problem; writes the best layout, reports the assessment, exits 1 unless complete."""
    try:
        levels = load_all(files)
        if levels.problem is None:
            _fail("solving needs a problem")
        params = dict(item.split("=", 1) for item in (param or []))
        if root is not None:
            service = LocalService(root)
            run_id = service.submit(
                levels.problem,
                Request(
                    solver=solver,
                    params=params,
                    seed=seed,
                    units=units,
                    seconds=seconds,
                    router=router,
                ),
            )
            recorded = service.result(run_id)
            if recorded.layout is None:
                _fail(f"run {run_id}: {recorded.state} {recorded.error}")
            write_out(write(recorded.layout, levels.problem), out)
            typer.echo(f"run {run_id}: {recorded.state}", err=True)
            typer.echo(report(recorded.assessment), err=True)
            raise typer.Exit(code=0 if recorded.state == "done" else 1)
        result = run_solve(
            levels.problem,
            solver=solver,
            seed=seed,
            budget=Budget(units=units, seconds=seconds),
            params=params,
            router=router,
        )
    except KohakuLayoutError as exc:
        _fail(str(exc))
    write_out(write(result.layout, levels.problem), out)
    typer.echo(
        f"{result.outcome}: {result.attempts} attempts, {result.refusals} refusals",
        err=True,
    )
    typer.echo(report(result.assessment), err=True)
    if result.outcome != "complete":
        raise typer.Exit(code=1)


@app.command()
def runs(root: Path) -> None:
    """List the runs recorded under a root and their state."""
    for status in list_runs(root):
        best = status.best_metrics
        summary = (
            f"area={best.get('area')} missing={best.get('missing')} unrouted={best.get('unrouted')}"
            if best
            else "no best yet"
        )
        typer.echo(
            f"{status.run}  {status.state:<10} {status.outcome or '-':<10} {summary}"
        )


def main() -> None:
    app()
