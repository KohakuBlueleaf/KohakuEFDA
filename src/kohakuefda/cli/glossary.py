"""``kohakuefda glossary``: EN / zh-TW / zh-CN names of machines, logistics units and items."""

import logging
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from kohakuefda.cli.data import DEFAULT_ROOT, load_dataset

log = logging.getLogger(__name__)
console = Console()


def glossary_cmd(
    what: str = typer.Argument("machines", help="machines | logistics | items | all"),
    version: str = typer.Option("", "--version", "-v", help="Dataset version id."),
    root: Path = typer.Option(DEFAULT_ROOT, "--root"),
    missing: bool = typer.Option(
        False, "--missing", help="Only rows lacking a zh-TW name."
    ),
) -> None:
    """Print the trilingual glossary from the dataset."""
    log.debug("glossary %s (missing only: %s)", what, missing)
    dataset = load_dataset(root, version)
    collections = {
        "machines": dataset.machines,
        "logistics": dataset.logistics,
        "items": dataset.items,
    }
    chosen = collections if what == "all" else {what: collections[what]}
    for name, collection in chosen.items():
        table = Table(title=f"{name} ({dataset.version.id})")
        for col in ("id", "en", "zh-TW", "zh-CN"):
            table.add_column(col)
        rows = sorted(collection.values(), key=lambda r: r.names.en)
        for record in rows:
            if missing and record.names.zh_tw:
                continue
            table.add_row(
                record.id, record.names.en, record.names.zh_tw, record.names.zh_cn
            )
        console.print(table)
