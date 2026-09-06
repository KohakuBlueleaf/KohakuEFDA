"""Strict build-time configuration and extension catalogs."""

import math
from collections.abc import Callable
from dataclasses import dataclass, field

from kohakuefda.framework.control import ConfigurationError

WORLD_DEFAULTS = {
    "w_wire": 1.0,
    "w_unit": 2.0,
    "w_pull": 0.25,
    "w_shape": 2.0,
    "w_over": 6.0,
    "w_pylon": 12.0,
    "route_iterations": 30,
    "present_cost": 2.0,
    "present_growth": 1.5,
    "turn_cost": 0.5,
    "bridge_cost": 4.0,
    "history_cost": 1.0,
    "pylon": "power_diffuser_1",
    "entry_sides": "NW",
    "frame_every": 20,
}
RUNTIME_DEFAULTS = {
    "seed": 0,
    "workers": 1,
    "max_actions": 0,
    "seconds": 0.0,
    "backend": "auto",
    "check_rates": True,
}


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
