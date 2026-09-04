"""Assemble the dataset for one raw table set, attaching wiki zh-TW names."""

import logging
from pathlib import Path

from kohakuefda.data.fetch import load_source_manifest, raw_dir
from kohakuefda.data.normalize.basements import build_basements
from kohakuefda.data.normalize.items import build_items, name_contents
from kohakuefda.data.normalize.logistics import build_constants, build_logistics
from kohakuefda.data.normalize.machines import build_machines
from kohakuefda.data.normalize.power import build_pylons
from kohakuefda.data.normalize.recipes import build_recipes
from kohakuefda.data.normalize.resources import build_resources
from kohakuefda.data.normalize.sinks import (
    build_activations,
    build_dumps,
    build_env_gases,
)
from kohakuefda.data.normalize.tables import RawTables, names_of
from kohakuefda.data.wiki_names import (
    WIKI_NAMES_FILE,
    load_wiki_names,
    title_candidates,
)
from kohakuefda.model.dataset import Dataset, DatasetVersion
from kohakuefda.model.names import Names

log = logging.getLogger(__name__)


def _tech_names(tables: RawTables) -> dict[str, Names]:
    out: dict[str, Names] = {}
    for node_id, record in tables["FacSTTNodeTable"].items():
        en, cn = names_of(record)
        if en:
            out[node_id] = Names(en=en, zh_cn=cn)
    return out


def _attach_tc(names: Names, wiki: dict[str, dict[str, str]]) -> Names:
    for title in title_candidates(names.en):
        entry = wiki.get(title)
        if entry and entry.get("tc"):
            return names.model_copy(update={"zh_tw": entry["tc"]})
    return names


def build_dataset(root: Path, version_id: str) -> Dataset:
    """Dataset from ``data/raw/<version_id>/`` (tables and cached wiki names)."""
    source = load_source_manifest(root, version_id)
    version_dir = raw_dir(root, version_id)
    tables = RawTables(version_dir / "TableCfg")
    wiki = load_wiki_names(version_dir / WIKI_NAMES_FILE)
    items = build_items(tables)
    machines = build_machines(tables)
    logistics = build_logistics(tables)
    recipes = build_recipes(tables)
    for collection in (items, machines, logistics):
        for record in collection.values():
            record.names = _attach_tc(record.names, wiki)
    items = name_contents(items, recipes)
    log.debug(
        "assembled dataset %s: %d items, %d machines, %d recipes, %d wiki name(s)",
        source.sourceVersion,
        len(items),
        len(machines),
        len(recipes),
        len(wiki),
    )
    return Dataset(
        version=DatasetVersion(
            id=source.sourceVersion,
            game_version=source.gameVersion,
            hotfix=source.hotfixVersion,
            source=source.source,
            published_at=source.exportedAt,
        ),
        items=items,
        machines=machines,
        recipes=recipes,
        logistics=logistics,
        constants=build_constants(tables),
        basements=build_basements(),
        tech_names=_tech_names(tables),
        activations=build_activations(tables),
        dumps=build_dumps(tables),
        env_gases=build_env_gases(tables),
        resources=build_resources(),
        pylons=build_pylons(tables),
    )


def wiki_titles(dataset: Dataset) -> list[str]:
    """English page titles worth querying on the wiki: machines, logistics units and items."""
    names = {m.names.en for m in dataset.machines.values()}
    names |= {u.names.en for u in dataset.logistics.values()}
    names |= {i.names.en for i in dataset.items.values()}
    titles: set[str] = set()
    for name in names:
        if name and not name.startswith("item_"):
            titles.update(title_candidates(base_name(name)))
    return sorted(titles)


def base_name(name: str) -> str:
    """A display name without the contents suffix the dataset adds to filled containers."""
    if name.endswith(")") and " (" in name:
        return name[: name.rindex(" (")]
    return name


def dataset_path(root: Path, version_id: str) -> Path:
    return root / version_id / "dataset.json"
