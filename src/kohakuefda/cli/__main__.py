"""``kohakuefda`` command tree built on typer with rich output."""

import logging
import sys
from pathlib import Path

import typer
from rich.console import Console

from kohakuefda import __version__
from kohakuefda.cli.cells import netlist_cmd
from kohakuefda.cli.data import data_app
from kohakuefda.cli.diff import diff_cmd
from kohakuefda.cli.glossary import glossary_cmd
from kohakuefda.cli.layout_cmds import check_cmd, layout_cmd, render_cmd
from kohakuefda.cli.plan import plan_cmd
from kohakuefda.cli.view import view_cmd
from kohakuefda.util.logging import setup

log = logging.getLogger(__name__)
console = Console()
app = typer.Typer(
    name="kohakuefda",
    help="End Field Design Automation: plan, lay out and verify Endfield AIC factories.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
app.add_typer(data_app, name="data")
data_app.command("diff")(diff_cmd)
app.command("glossary")(glossary_cmd)
app.command("plan")(plan_cmd)
app.command("check")(check_cmd)
app.command("render")(render_cmd)
app.command("netlist")(netlist_cmd)
app.command("layout")(layout_cmd)
app.command("serve")(view_cmd)
app.command("view")(view_cmd)


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"kohakuefda {__version__}")
        raise typer.Exit()


@app.callback()
def root(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Print version.",
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Log at DEBUG instead of INFO."
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Log warnings and errors only."
    ),
    log_file: Path | None = typer.Option(
        None, "--log-file", help="Also write the log to this file, without colour."
    ),
) -> None:
    """Entry point shared by every subcommand."""
    level = "DEBUG" if verbose else ("WARNING" if quiet else "INFO")
    setup(level, path=log_file)
    log.debug("kohakuefda %s starting", __version__, argv=" ".join(sys.argv[1:]))


def main() -> int:
    """Console-script entry; returns the process exit status."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    app()
    return 0
