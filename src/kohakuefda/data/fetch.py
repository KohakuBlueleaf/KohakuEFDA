"""Download the pinned game tables into ``data/raw/<versionId>/TableCfg/`` with a SHA manifest."""

import hashlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import httpx

from kohakuefda.data.manifest import Manifest, ManifestVersion, fetch_manifest
from kohakuefda.data.mirror import resolve_ref, table_url
from kohakuefda.data.sources import AKEDATA_BASE_URL, FACTORY_TABLES
from kohakuefda.model.base import EfdaModel

log = logging.getLogger(__name__)
SOURCE_MANIFEST = "source-manifest.json"


class TableEntry(EfdaModel):
    file: str
    sha256: str
    url: str


class SourceManifest(EfdaModel):
    """Provenance of one raw table set: version, source, fetch time and per-table hashes."""

    schemaVersion: int = 1
    source: str
    sourceVersion: str
    gameVersion: str
    hotfixVersion: str
    exportedAt: str
    tables: dict[str, TableEntry] = {}


def raw_dir(root: Path, version_id: str) -> Path:
    return root / "raw" / version_id


def _download(client: httpx.Client, url: str) -> bytes:
    response = client.get(url)
    response.raise_for_status()
    json.loads(response.content)
    return response.content


def _write_table(dest: Path, table: str, payload: bytes) -> TableEntry:
    path = dest / "TableCfg" / f"{table}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return TableEntry(
        file=f"TableCfg/{table}.json",
        sha256=hashlib.sha256(payload).hexdigest(),
        url="",
    )


def fetch_tables(
    client: httpx.Client,
    root: Path,
    version_id: str = "latest",
    tables: tuple[str, ...] = FACTORY_TABLES,
    prefer: str = "mirror",
    manifest: Manifest | None = None,
) -> SourceManifest:
    """Fetch ``tables`` for ``version_id``; the mirror inlines text, AKEData carries text hashes."""
    manifest = manifest or fetch_manifest(client)
    version = manifest.get(version_id)
    dest = raw_dir(root, version.id)
    mirror_ref: str | None = None
    entries: dict[str, TableEntry] = {}
    for table in tables:
        payload, url = _fetch_one(client, version, table, prefer, mirror_ref)
        if url.startswith("https://raw.githubusercontent.com") and mirror_ref is None:
            mirror_ref = url.split("/")[5]
        entry = _write_table(dest, table, payload)
        entries[table] = entry.model_copy(update={"url": url})
        log.info("fetched %s from %s", table, url)
    source = SourceManifest(
        source=prefer,
        sourceVersion=version.id,
        gameVersion=version.gameVersion,
        hotfixVersion=version.hotfixVersion,
        exportedAt=datetime.now(UTC).isoformat(),
        tables=entries,
    )
    (dest / SOURCE_MANIFEST).write_text(
        source.model_dump_json(indent=1) + "\n", encoding="utf-8"
    )
    log.info("fetched %d table(s) for %s via %s", len(entries), version.id, prefer)
    return source


def _fetch_one(
    client: httpx.Client,
    version: ManifestVersion,
    table: str,
    prefer: str,
    mirror_ref: str | None,
) -> tuple[bytes, str]:
    akedata_url = f"{AKEDATA_BASE_URL}{version.tableCfgPath}/{table}.json"
    order = ["akedata", "mirror"] if prefer == "akedata" else ["mirror", "akedata"]
    last_error: Exception | None = None
    for source in order:
        try:
            if source == "akedata":
                return _download(client, akedata_url), akedata_url
            ref = mirror_ref or resolve_ref(client, version.hotfixVersion)
            url = table_url(ref, table)
            return _download(client, url), url
        except (httpx.HTTPError, ValueError) as error:
            last_error = error
    raise RuntimeError(f"could not fetch {table} for {version.id}: {last_error}")


def load_source_manifest(root: Path, version_id: str) -> SourceManifest:
    path = raw_dir(root, version_id) / SOURCE_MANIFEST
    return SourceManifest.model_validate(json.loads(path.read_text(encoding="utf-8")))


def verify_tables(root: Path, version_id: str) -> list[str]:
    """Names of tables whose file is missing or whose SHA-256 differs from the manifest."""
    source = load_source_manifest(root, version_id)
    dest = raw_dir(root, version_id)
    bad: list[str] = []
    for table, entry in source.tables.items():
        path = dest / entry.file
        if (
            not path.exists()
            or hashlib.sha256(path.read_bytes()).hexdigest() != entry.sha256
        ):
            bad.append(table)
    if bad:
        log.warning("verify %s: %d bad table(s): %s", version_id, len(bad), bad)
    return bad
