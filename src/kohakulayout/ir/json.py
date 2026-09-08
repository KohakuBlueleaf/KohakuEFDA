"""Canonical JSON in and out, for any level, dispatched on the ``level`` key."""

import json
from typing import Any

from kohakulayout.errors import IRError
from kohakulayout.ir.base import LEVELS, Level, canonical_json


def dumps(level: Level) -> str:
    return level.to_json()


def loads(text: str) -> Level:
    try:
        data: Any = json.loads(text)
    except json.JSONDecodeError as exc:
        raise IRError(f"not JSON: {exc}") from exc
    if not isinstance(data, dict) or "level" not in data:
        raise IRError("a level JSON carries a 'level' key")
    name = data.pop("level")
    cls = LEVELS.get(name)
    if cls is None:
        raise IRError(f"unknown level {name!r}; known: {sorted(LEVELS)}")
    return cls.model_validate(data)


def pretty(level: Level) -> str:
    return json.dumps(level.content(), indent=2, sort_keys=True, ensure_ascii=False)


__all__ = ["canonical_json", "dumps", "loads", "pretty"]
