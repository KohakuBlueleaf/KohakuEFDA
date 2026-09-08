"""The stage's settings and the studio's catalogue: strict overrides, typed by their defaults.

Kept beside the layout stage since the framework the project used to carry these in
retired; KohakuLayout has its own params on each solver.
"""

import math
from collections.abc import Callable
from dataclasses import dataclass, field


class ConfigurationError(ValueError):
    """A setting the stage does not know, or a value it cannot take."""


def settings_of(defaults: dict, values: dict | None = None) -> dict:
    """Resolve overrides, reject unknown names and non-finite numeric values."""
    result = dict(defaults)
    for key, value in (values or {}).items():
        if key not in defaults:
            raise ConfigurationError(f"unknown setting {key!r}")
        kind = type(defaults[key])
        try:
            if kind is bool:
                if not isinstance(value, bool):
                    raise ValueError("expected a boolean")
                parsed = value
            else:
                parsed = kind(value)
                if kind is int and isinstance(value, float) and value != parsed:
                    raise ValueError("expected a whole number")
            if kind in (float, int) and (
                not math.isfinite(parsed) or (key != "seed" and parsed < 0)
            ):
                raise ValueError("expected a finite nonnegative value")
            result[key] = parsed
        except (TypeError, ValueError, OverflowError) as error:
            raise ConfigurationError(f"{key}: {error}") from error
    return result


@dataclass(frozen=True)
class Entry:
    name: str
    factory: Callable
    defaults: dict = field(default_factory=dict)
    description: str = ""
    version: str = "1"

    def build(self, settings: dict | None = None):
        return self.factory(**settings_of(self.defaults, settings))


class Catalog:
    """An application-owned registry; the framework imports no concrete solver."""

    def __init__(self) -> None:
        self._entries: dict[str, Entry] = {}

    def register(self, entry: Entry) -> None:
        if entry.name in self._entries:
            raise ConfigurationError(f"duplicate extension {entry.name!r}")
        self._entries[entry.name] = entry

    def get(self, name: str) -> Entry:
        if name not in self._entries:
            raise ConfigurationError(f"unknown extension {name!r}")
        return self._entries[name]

    def describe(self) -> list[dict]:
        return [
            {
                "name": e.name,
                "version": e.version,
                "description": e.description,
                "defaults": dict(e.defaults),
                "parameter_types": {
                    key: type(value).__name__ for key, value in e.defaults.items()
                },
                "parallel": bool(getattr(e.factory, "parallel", False)),
            }
            for e in self._entries.values()
        ]
