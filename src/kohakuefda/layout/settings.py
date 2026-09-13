"""The layout stage's settings, its solver table and the studio's catalogue.

Overrides are typed by their defaults and unknown names refused (``settings_of``).
The studio and the CLI keep their flat settings (``solver``, ``seed``, ``seconds``,
``max_actions``, ``backend``, ``solver_options``); this module maps them onto a framework
solver id, its params and a budget. The project's own solvers (``kohakuefda.solvers``: the
regional construction and the local searches over it) stand behind the names
``regional``, ``hc`` and ``sa``; ``baseline`` and ``inorder`` are the framework's.
``ROUTER_COSTS`` carries the routing costs on a ten-times scale: a step 10, a turn 5, a
bridge 40, a displaced wire's cell 20, a pylon's cell nothing (a lane displaces it and the
cover is redone), and the detour rule that a path may cost the span across stretched by
2.5 plus 16 cells. ``ROUTER_NEGOTIATION`` keeps placement-time routing: another net's wire
is a wall to a lane, a route never rips a wire, a placement whose lanes find no path is
refused at once, and only a footprint displaces wires, which re-route; its lanes are laid
as a bundle with costs summed as single floats on the same scale. The catalogue the
studio lists is the framework's, described from each solver's declared params under the
project's legacy names.
"""

import json
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from kohakuefda.layout.router import EndfieldRouter
from kohakuefda.solvers import EndfieldAnneal, EndfieldClimb, EndfieldRegional
from kohakulayout.engine import Budget
from kohakulayout.errors import SolverError
from kohakulayout.solvers import get, known
from kohakulayout.solvers.params import resolve
from kohakulayout.state.router.protocol import Costs


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


SOLVER_NAMES: dict[str, str] = {
    "hc": EndfieldClimb.id,
    "sa": EndfieldAnneal.id,
    "baseline": "baseline",
    "regional": EndfieldRegional.id,
    "inorder": "inorder",
}
DESCRIPTIONS: dict[str, str] = {
    "hc": "Regional construction, then hill climbing over the coordinate moves.",
    "sa": "Regional construction, then simulated annealing with cooling by charged work.",
    "baseline": "A first-complete spread on a lattice, then greedy shrinking.",
    "regional": "Seeded frontier construction on a clearance map, then shrinking.",
    "inorder": "The pack's anchors in order, one attempt per cell; the null strategy.",
}
LAYOUT_DEFAULTS: dict[str, Any] = {
    "solver": "hc",
    "seed": 0,
    "seconds": 600.0,
    "max_actions": 0,
    "backend": "auto",
    "frame_every": 100,
    "spread_attempts": 0,
    "workers": 0,
    "solver_options": "{}",
}
LayoutError = ConfigurationError
DEFAULT_UNITS = 20_000
ROUTER_COSTS: dict[str, float] = {
    "step": 10,
    "turn": 5,
    "crossing": 40,
    "ripup": 20,
    "displace": 0,
    "detour": 25.0,
    "slack": 160.0,
}
ROUTER_NEGOTIATION: dict[str, Any] = {
    "max_rips": 0,
    "lanes": True,
    "wire_model": "lanes",
    "float_scale": 10,
}


def framework_id(name: str) -> str:
    """The framework solver behind a project name; a framework id passes through."""
    if name in SOLVER_NAMES:
        return SOLVER_NAMES[name]
    if name in known():
        return name
    raise ConfigurationError(
        f"unknown solver {name!r}; known: {sorted(SOLVER_NAMES)} and {sorted(known())}"
    )


def solver_options(params: dict[str, Any]) -> dict[str, Any]:
    """The solver's own params from the ``solver_options`` JSON object."""
    try:
        options = json.loads(params.get("solver_options") or "{}")
    except (ValueError, TypeError) as error:
        raise ConfigurationError("solver_options must be a JSON object") from error
    if not isinstance(options, dict):
        raise ConfigurationError("solver_options must be a JSON object")
    return options


LIMITS: dict[str, int] = {"spread_attempts": 4096, "attempts": 4096}


def typed_option(param: Any, value: Any) -> Any:
    """The option as the solver declared it; a wrong kind is refused rather than coerced."""
    kind = param.type
    if kind == "bool":
        if not isinstance(value, bool):
            raise ConfigurationError(f"{param.name}: expected a boolean")
        return value
    if kind == "int":
        if (
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or value != int(value)
        ):
            raise ConfigurationError(f"{param.name}: expected a whole number")
        if value < 0:
            raise ConfigurationError(f"{param.name}: expected a nonnegative value")
        return int(value)
    if kind in ("float", "seconds", "fraction"):
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ConfigurationError(f"{param.name}: expected a number")
        if not math.isfinite(value) or value < 0:
            raise ConfigurationError(
                f"{param.name}: expected a finite nonnegative value"
            )
        return float(value)
    if kind == "choice" and value not in param.choices:
        raise ConfigurationError(
            f"{param.name}: {value!r} is not one of {param.choices}"
        )
    return value


def solver_of(params: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """The framework solver id and its typed options for flat layout settings; the solver validates them."""
    solver_id = framework_id(str(params["solver"]))
    options = solver_options(params)
    solver = get(solver_id)
    declared = {p.name: p for p in solver.params}
    spread = int(params.get("spread_attempts") or 0)
    if spread and "spread_attempts" in declared:
        options.setdefault("spread_attempts", spread)
    elif spread and "attempts" in declared:
        options.setdefault("attempts", spread)
    unknown = sorted(set(options) - set(declared))
    if unknown:
        raise ConfigurationError(
            f"solver {params['solver']!r} takes no option {unknown}; it declares {sorted(declared)}"
        )
    typed = {
        name: typed_option(declared[name], value) for name, value in options.items()
    }
    for name, value in typed.items():
        if name in LIMITS and value > LIMITS[name]:
            raise ConfigurationError(f"{name}: at most {LIMITS[name]}")
    try:
        solver.opts = resolve(solver.params, typed)
        validate = getattr(solver, "validate", None)
        if validate is not None:
            validate()
    except SolverError as error:
        raise ConfigurationError(str(error)) from error
    return solver_id, typed


def router_of() -> EndfieldRouter:
    """The project's router with its lane order, wire model and costs."""
    router = EndfieldRouter(**ROUTER_NEGOTIATION)
    router.costs = Costs(**ROUTER_COSTS)
    return router


def budget_of(params: dict[str, Any]) -> Budget:
    """The framework budget: seconds and actions as given; neither given means ``DEFAULT_UNITS`` actions."""
    seconds = float(params.get("seconds") or 0) or None
    units = int(params.get("max_actions") or 0) or None
    if seconds is None and units is None:
        units = DEFAULT_UNITS
    return Budget(units=units, seconds=seconds)


def _defaults_of(solver_id: str) -> dict[str, Any]:
    return {p.name: p.default for p in get(solver_id).params}


class Options:
    """The catalogue's factory: the options as given; ``parallel`` says whether workers apply."""

    def __init__(self, parallel: bool) -> None:
        self.parallel = parallel

    def __call__(self, **options: Any) -> dict[str, Any]:
        return options


PARALLEL = frozenset({"baseline"})


def catalogue() -> Catalog:
    """The studio's catalogue: every project name with the framework solver's params as its defaults."""
    table = Catalog()
    for name, solver_id in SOLVER_NAMES.items():
        table.register(
            Entry(
                name,
                Options(name in PARALLEL),
                _defaults_of(solver_id),
                DESCRIPTIONS.get(name, ""),
            )
        )
    return table


SOLVERS = catalogue()

__all__ = [
    "DEFAULT_UNITS",
    "DESCRIPTIONS",
    "LAYOUT_DEFAULTS",
    "LIMITS",
    "ROUTER_COSTS",
    "SOLVERS",
    "SOLVER_NAMES",
    "Catalog",
    "ConfigurationError",
    "Entry",
    "LayoutError",
    "budget_of",
    "catalogue",
    "framework_id",
    "router_of",
    "settings_of",
    "solver_of",
    "solver_options",
    "typed_option",
]
