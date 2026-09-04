"""Update checker: is a newer game version safe to adopt blindly, or does it need a handler?"""

import json
import logging
from pathlib import Path

from rich.console import Console
from rich.table import Table

from kohakuefda.data.fetch import fetch_tables, raw_dir
from kohakuefda.data.manifest import fetch_manifest, make_client
from kohakuefda.data.normalize.tables import RawTables
from kohakuefda.data.sources import FACTORY_TABLES

log = logging.getLogger(__name__)
SCHEMA_TABLES = (
    "FactoryBuildingTable",
    "FactoryMachineCraftTable",
    "FactoryMachineCraftGroupTable",
    "FactoryMachineCrafterTable",
    "FactoryItemTable",
    "FactoryConst",
    "FacBlueprintConst",
)


def _record_keys(table: dict) -> set[str]:
    keys: set[str] = set()
    for record in table.values():
        if isinstance(record, dict):
            keys |= set(record)
    return keys


def _building_kinds(table: dict) -> set[str]:
    return {str(r.get("type")) for r in table.values() if isinstance(r, dict)}


def _modes(table: dict) -> set[str]:
    return {m["modeName"] for r in table.values() for m in r.get("modeMap", [])}


def classify(old: RawTables, new: RawTables) -> tuple[list[str], list[str]]:
    """``(blind_safe, needs_handler)`` findings between two raw table sets."""
    safe: list[str] = []
    handler: list[str] = []
    for name in SCHEMA_TABLES:
        added = _record_keys(new[name]) - _record_keys(old[name])
        removed = _record_keys(old[name]) - _record_keys(new[name])
        if added or removed:
            handler.append(
                f"{name}: fields added {sorted(added)} removed {sorted(removed)}"
            )
    kinds = _building_kinds(new["FactoryBuildingTable"]) - _building_kinds(
        old["FactoryBuildingTable"]
    )
    if kinds:
        handler.append(f"new building types {sorted(kinds)}")
    modes = _modes(new["FactoryMachineCrafterTable"]) - _modes(
        old["FactoryMachineCrafterTable"]
    )
    if modes:
        handler.append(f"new machine modes {sorted(modes)}")
    for name in FACTORY_TABLES:
        if not old.has(name) or not new.has(name):
            handler.append(
                f"{name}: present only in {'new' if new.has(name) else 'old'}"
            )
            continue
        added_ids = set(new[name]) - set(old[name])
        removed_ids = set(old[name]) - set(new[name])
        changed = sum(
            1 for k in set(new[name]) & set(old[name]) if new[name][k] != old[name][k]
        )
        if added_ids or removed_ids or changed:
            safe.append(f"{name}: +{len(added_ids)} -{len(removed_ids)} ~{changed}")
    const_keys = set(new["FactoryConst"]) - set(old["FactoryConst"])
    if const_keys:
        handler.append(f"new FactoryConst keys {sorted(const_keys)}")
    return safe, handler


def run_check(root: Path, pinned: str, console: Console) -> None:
    """Fetch the newest version next to ``pinned`` and print the classification."""
    with make_client() as client:
        manifest = fetch_manifest(client)
        latest = manifest.latest
        pinned = pinned or _newest_built(root)
        log.info("checking %s against latest published %s", pinned, latest)
        if pinned == latest:
            console.print(f"[green]pinned {pinned} is the latest published version[/]")
            return
        if not (raw_dir(root, latest) / "source-manifest.json").exists():
            fetch_tables(client, root, latest, manifest=manifest)
    old = RawTables(raw_dir(root, pinned) / "TableCfg")
    new = RawTables(raw_dir(root, latest) / "TableCfg")
    safe, handler = classify(old, new)
    log.info(
        "check %s -> %s: %d blind-safe, %d needing a handler",
        pinned,
        latest,
        len(safe),
        len(handler),
    )
    table = Table(title=f"{pinned} → {latest}")
    table.add_column("class")
    table.add_column("finding")
    for line in handler:
        table.add_row("[red]needs handler[/]", line)
    for line in safe:
        table.add_row("[green]blind-safe[/]", line)
    console.print(table)
    verdict = "needs a handler before bumping" if handler else "safe to bump blindly"
    console.print(f"verdict: [bold]{verdict}[/]")


def _newest_built(root: Path) -> str:
    built = sorted(p.name for p in root.iterdir() if (p / "dataset.json").exists())
    if not built:
        raise FileNotFoundError(f"no built dataset under {root}")
    return built[-1]


def diff_ids(root: Path, old_id: str, new_id: str) -> dict[str, dict[str, list[str]]]:
    """Per-collection added/removed ids between two built datasets."""
    old = json.loads((root / old_id / "dataset.json").read_text("utf-8"))
    new = json.loads((root / new_id / "dataset.json").read_text("utf-8"))
    out: dict[str, dict[str, list[str]]] = {}
    for key in ("items", "machines", "recipes", "logistics"):
        out[key] = {
            "added": sorted(set(new[key]) - set(old[key])),
            "removed": sorted(set(old[key]) - set(new[key])),
        }
    return out
