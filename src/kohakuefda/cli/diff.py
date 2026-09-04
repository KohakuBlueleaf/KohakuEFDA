"""``kohakuefda data diff``: id-level differences between two built datasets."""

import logging
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from kohakuefda.cli.data import DEFAULT_ROOT
from kohakuefda.data.check import diff_ids

log = logging.getLogger(__name__)
console = Console()


def diff_cmd(
    old: str = typer.Argument(..., help="Older dataset version id."),
    new: str = typer.Argument(..., help="Newer dataset version id."),
    root: Path = typer.Option(DEFAULT_ROOT, "--root"),
) -> None:
    """Show added and removed ids per collection between two dataset versions."""
    log.info("diffing dataset %s -> %s", old, new)
    result = diff_ids(root, old, new)
    table = Table(title=f"{old} → {new}")
    for col in ("collection", "added", "removed"):
        table.add_column(col)
    for collection, change in result.items():
        table.add_row(
            collection,
            ", ".join(change["added"]) or "-",
            ", ".join(change["removed"]) or "-",
        )
    console.print(table)
