"""Item, machine and logistics icons from endfield.wiki.gg, stored under ``<root>/icons/``.

Every entity's English name gives wiki file titles (``File:<name>.png`` and the name's
variants); ``imageinfo`` resolves them in batches and each hit is downloaded once. The index
``<root>/icons/index.json`` maps ``kind`` → ``id`` → relative file, plus the ids without an icon.
"""

import json
import logging
from pathlib import Path

import httpx

from kohakuefda.data.normalize.build import base_name
from kohakuefda.data.sources import WIKI_API_URL
from kohakuefda.data.wiki_names import title_candidates
from kohakuefda.model.dataset import Dataset

log = logging.getLogger(__name__)

KINDS = ("items", "machines", "logistics")
INDEX_FILE = "index.json"
BATCH = 50
IconIndex = dict[str, dict[str, str] | list[str]]


def icons_dir(root: Path) -> Path:
    return root / "icons"


def icon_titles(dataset: Dataset) -> dict[tuple[str, str], list[str]]:
    """Wiki title candidates per ``(kind, id)`` from the English names."""
    tables = {
        "items": dataset.items,
        "machines": dataset.machines,
        "logistics": dataset.logistics,
    }
    out: dict[tuple[str, str], list[str]] = {}
    for kind, table in tables.items():
        for entity_id, entity in table.items():
            name = base_name(entity.names.en)
            if name and not name.startswith("item_"):
                out[(kind, entity_id)] = title_candidates(name)
    return out


def _file_key(title: str) -> str:
    """The bare name of a ``File:<name>.png`` title as the API normalises it."""
    name = title.removeprefix("File:")
    name = name.removesuffix(".png")
    return name.replace("_", " ").strip().lower()


def query_files(client: httpx.Client, titles: list[str]) -> dict[str, str]:
    """``{normalised title: url}`` for every ``File:<title>.png`` that exists on the wiki."""
    out: dict[str, str] = {}
    unique = list(dict.fromkeys(titles))
    for start in range(0, len(unique), BATCH):
        chunk = unique[start : start + BATCH]
        params = {
            "action": "query",
            "prop": "imageinfo",
            "iiprop": "url",
            "redirects": "1",
            "format": "json",
            "titles": "|".join(f"File:{t}.png" for t in chunk),
        }
        response = client.get(WIKI_API_URL, params=params)
        response.raise_for_status()
        query = response.json().get("query", {})
        back: dict[str, str] = {}
        for entry in query.get("normalized", []) + query.get("redirects", []):
            back[_file_key(entry["to"])] = back.get(
                _file_key(entry["from"]), _file_key(entry["from"])
            )
        for page in query.get("pages", {}).values():
            info = page.get("imageinfo")
            if not info or "missing" in page:
                continue
            key = _file_key(page["title"])
            out[back.get(key, key)] = info[0]["url"]
    return out


def load_icon_index(root: Path) -> IconIndex:
    path = icons_dir(root) / INDEX_FILE
    if not path.is_file():
        return {kind: {} for kind in KINDS} | {"missing": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save_icon_index(root: Path, index: IconIndex) -> None:
    path = icons_dir(root) / INDEX_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(index, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )


def fetch_icons(
    client: httpx.Client, dataset: Dataset, root: Path, refresh: bool = False
) -> IconIndex:
    """Resolve and download every missing icon; returns the updated index."""
    index = load_icon_index(root)
    wanted = {
        key: candidates
        for key, candidates in icon_titles(dataset).items()
        if refresh or key[1] not in index.get(key[0], {})
    }
    urls = query_files(client, [t for cs in wanted.values() for t in cs])
    missing: list[str] = []
    for (kind, entity_id), candidates in sorted(wanted.items()):
        url = next(
            (urls[_file_key(t)] for t in candidates if _file_key(t) in urls), None
        )
        if url is None:
            missing.append(f"{kind}/{entity_id}")
            continue
        target = icons_dir(root) / kind / f"{entity_id}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        response = client.get(url)
        response.raise_for_status()
        target.write_bytes(response.content)
        index.setdefault(kind, {})[entity_id] = f"{kind}/{entity_id}.png"
        log.info("icon %s/%s ← %s", kind, entity_id, url)
    known = {
        f"{kind}/{entity_id}" for kind in KINDS for entity_id in index.get(kind, {})
    }
    index["missing"] = sorted((set(index.get("missing", [])) | set(missing)) - known)
    save_icon_index(root, index)
    log.info("icons: %d fetched, %d missing", len(wanted) - len(missing), len(missing))
    return index
