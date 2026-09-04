"""``kohakuefda data`` handlers: fetch, check, diff, show."""

import logging
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from kohakuefda.data.check import run_check
from kohakuefda.data.fetch import fetch_tables, raw_dir, verify_tables
from kohakuefda.data.icons import KINDS, fetch_icons, icons_dir
from kohakuefda.data.manifest import fetch_manifest, make_client
from kohakuefda.data.normalize.build import build_dataset, dataset_path, wiki_titles
from kohakuefda.data.wiki_names import (
    WIKI_NAMES_FILE,
    fetch_wiki_names,
    load_wiki_names,
    save_wiki_names,
)
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.names import Lang

log = logging.getLogger(__name__)
console = Console()
data_app = typer.Typer(help="Fetch, check, diff and show the pinned game dataset.")
DEFAULT_ROOT = Path("data")


def _resolve_version(version: str) -> str:
    if version != "latest":
        return version
    with make_client() as client:
        return fetch_manifest(client).latest


@data_app.command("fetch")
def fetch_cmd(
    version: str = typer.Option(
        "latest", "--version", "-v", help="Manifest version id or 'latest'."
    ),
    root: Path = typer.Option(
        DEFAULT_ROOT, "--root", help="Data root holding raw/ and <version>/."
    ),
    source: str = typer.Option(
        "mirror", "--source", help="Preferred source: mirror (inline text) or akedata."
    ),
    wiki: bool = typer.Option(
        True, "--wiki/--no-wiki", help="Also fetch zh-TW names from the wiki."
    ),
    refresh: bool = typer.Option(
        False, "--refresh", help="Re-download even if the raw tables exist."
    ),
) -> None:
    """Download the pinned game tables, fetch wiki names, and build ``dataset.json``."""
    log.info("data fetch: version %s, source %s, wiki %s", version, source, wiki)
    with make_client() as client:
        manifest = fetch_manifest(client)
        version_id = manifest.get(version).id
        if refresh or not (raw_dir(root, version_id) / "source-manifest.json").exists():
            fetch_tables(client, root, version_id, prefer=source, manifest=manifest)
        bad = verify_tables(root, version_id)
        if bad:
            log.error("hash mismatch for %s: %s", version_id, bad)
            console.print(f"[red]hash mismatch:[/] {', '.join(bad)}")
            raise typer.Exit(code=1)
        dataset = build_dataset(root, version_id)
        names_file = raw_dir(root, version_id) / WIKI_NAMES_FILE
        if wiki and (refresh or not names_file.exists()):
            save_wiki_names(names_file, fetch_wiki_names(client, wiki_titles(dataset)))
            dataset = build_dataset(root, version_id)
    out = dataset_path(root, version_id)
    dataset.save(out)
    log.info(
        "built %s: %d items, %d machines, %d recipes",
        out,
        len(dataset.items),
        len(dataset.machines),
        len(dataset.recipes),
    )
    console.print(
        f"[green]built[/] {out}: {len(dataset.items)} items, {len(dataset.machines)} machines, "
        f"{len(dataset.recipes)} recipes, {len(dataset.logistics)} logistics units, "
        f"{len(load_wiki_names(names_file))} wiki names"
    )


@data_app.command("icons")
def icons_cmd(
    root: Path = typer.Option(DEFAULT_ROOT, "--root"),
    version: str = typer.Option(
        "", "--version", "-v", help="Dataset version id; default: newest built."
    ),
    refresh: bool = typer.Option(
        False, "--refresh", help="Re-download icons that are already stored."
    ),
) -> None:
    """Fetch item, machine and logistics icons from the wiki into ``<root>/icons/``."""
    dataset = load_dataset(root, version)
    log.info("data icons: dataset %s, refresh %s", dataset.version.id, refresh)
    with make_client() as client:
        index = fetch_icons(client, dataset, root, refresh)
    counts = ", ".join(f"{len(index.get(kind, {}))} {kind}" for kind in KINDS)
    console.print(
        f"[green]icons[/] under {icons_dir(root)}: {counts}; "
        f"{len(index.get('missing', []))} without an icon"
    )


@data_app.command("check")
def check_cmd(
    root: Path = typer.Option(DEFAULT_ROOT, "--root"),
    pinned: str = typer.Option(
        "", "--pinned", help="Pinned version id; default: newest built."
    ),
) -> None:
    """Compare the pinned version against the newest published one."""
    run_check(root, pinned, console)


@data_app.command("show")
def show_cmd(
    what: str = typer.Argument(
        "machines", help="machines | items | recipes | logistics | basements"
    ),
    version: str = typer.Option(
        "", "--version", "-v", help="Dataset version id; default: newest built."
    ),
    root: Path = typer.Option(DEFAULT_ROOT, "--root"),
    lang: str = typer.Option("en", "--lang", help="en | zh-TW | zh-CN"),
) -> None:
    """Browse the dataset as tables."""
    dataset = load_dataset(root, version)
    console.print(render_table(dataset, what, lang))


def newest_version(root: Path) -> str:
    candidates = sorted(p.name for p in root.iterdir() if (p / "dataset.json").exists())
    if not candidates:
        raise typer.BadParameter(
            f"no dataset under {root}; run 'kohakuefda data fetch' first"
        )
    return candidates[-1]


def load_dataset(root: Path, version: str = "") -> Dataset:
    path = dataset_path(root, version or newest_version(root))
    log.debug("loading dataset from %s", path)
    return Dataset.load(path)


def render_table(dataset: Dataset, what: str, lang: Lang) -> Table:
    table = Table(title=f"{what} ({dataset.version.id})")
    match what:
        case "machines":
            for col in (
                "id",
                "name",
                "size",
                "belt in/out",
                "pipe in/out",
                "power",
                "modes",
            ):
                table.add_column(col)
            for m in sorted(dataset.machines.values(), key=lambda m: m.names.en):
                belt = [p for p in m.ports if p.type == "belt"]
                pipe = [p for p in m.ports if p.type == "pipe"]
                table.add_row(
                    m.id,
                    m.names.get(lang),
                    f"{m.width}x{m.depth}x{m.height}",
                    f"{sum(p.direction == 'in' for p in belt)}/{sum(p.direction == 'out' for p in belt)}",
                    f"{sum(p.direction == 'in' for p in pipe)}/{sum(p.direction == 'out' for p in pipe)}",
                    str(m.power),
                    ",".join(x.name for x in m.modes),
                )
        case "items":
            for col in ("id", "name", "phase", "storable"):
                table.add_column(col)
            for i in sorted(dataset.items.values(), key=lambda i: i.names.en):
                table.add_row(
                    i.id,
                    i.names.get(lang),
                    i.phase.name.lower(),
                    "yes" if i.storable else "",
                )
        case "recipes":
            for col in ("id", "machine", "mode", "seconds", "inputs", "outputs", "env"):
                table.add_column(col)
            for r in sorted(
                dataset.recipes.values(), key=lambda r: (r.machine_id, r.id)
            ):
                table.add_row(
                    r.id,
                    r.machine_id,
                    r.mode,
                    str(r.seconds),
                    ", ".join(
                        f"{s.count} {dataset.items[s.item_id].names.get(lang)}"
                        for s in r.inputs
                    ),
                    ", ".join(
                        f"{s.count} {dataset.items[s.item_id].names.get(lang)}"
                        for s in r.outputs
                    ),
                    r.env or "",
                )
        case "logistics":
            for col in ("id", "name", "kind", "size", "per min", "ports"):
                table.add_column(col)
            for u in dataset.logistics.values():
                table.add_row(
                    u.id,
                    u.names.get(lang),
                    u.kind,
                    f"{u.width}x{u.depth}x{u.height}",
                    str(u.rate_per_min),
                    str(len(u.ports)),
                )
        case "basements":
            for col in ("id", "name", "region", "squares", "depot"):
                table.add_column(col)
            for b in dataset.basements.values():
                squares = ", ".join(
                    f"L{k}:{v[0]}x{v[1]}" if v else f"L{k}:?"
                    for k, v in b.square_by_level.items()
                )
                table.add_row(b.id, b.names.get(lang), b.region, squares, b.depot.kind)
        case _:
            raise typer.BadParameter(f"unknown collection {what!r}")
    return table
