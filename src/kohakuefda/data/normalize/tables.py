"""Loader for the raw ``TableCfg/*.json`` files of one version."""

import json
from pathlib import Path


class RawTables:
    """Lazy access to raw tables by name, e.g. ``tables["FactoryBuildingTable"]``."""

    def __init__(self, table_dir: Path) -> None:
        self.table_dir = table_dir
        self._cache: dict[str, dict] = {}

    def __getitem__(self, name: str) -> dict:
        if name not in self._cache:
            path = self.table_dir / f"{name}.json"
            self._cache[name] = json.loads(path.read_text(encoding="utf-8"))
        return self._cache[name]

    def has(self, name: str) -> bool:
        return (self.table_dir / f"{name}.json").exists()


def names_of(record: dict, key: str = "name") -> tuple[str, str]:
    """``(en, cn)`` from a ``{"cn": ..., "en": ...}`` field, empty strings when absent."""
    value = record.get(key) or {}
    return str(value.get("en", "")), str(value.get("cn", ""))


def as_int(value: object, default: int = 0) -> int:
    """Tables store numbers as strings; parse leniently."""
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(float(value))
