"""The layout stage's settings, its solver catalogue, the router and the budget.

Overrides are typed by their defaults and unknown names refused (``settings_of``). The
studio and the CLI keep flat settings (``solver``, ``seed``, ``seconds``,
``max_actions``, ``backend``, ``solver_options``); this module maps them onto a
framework solver id, its typed params and a budget. The catalogue lists every solver
the project and the framework ship, named by id without the ``endfield.`` prefix.
``ROUTER_COSTS`` are on a ten-times scale: a step 10, a turn 5, a bridge 40, a displaced
wire's cell 20, a pylon's cell nothing, a path at most the span stretched by 2.5 plus
16 cells. ``ROUTER_NEGOTIATION`` keeps placement-time routing: another net's wire is a
wall, a route never rips a wire, a placement whose lanes find no path is refused, and a
net's lanes are laid as one bundle.
"""

import json
import math
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from kohakuefda.layout.router import EndfieldRouter
from kohakuefda.solvers import SOLVER_IDS
from kohakulayout.engine import Budget
from kohakulayout.errors import SolverError
from kohakulayout.solvers import get, known
from kohakulayout.solvers.params import resolve
from kohakulayout.state.router.protocol import Costs

FRAMEWORK = "kohakulayout.solvers."
PREFIX = "endfield."
DESCRIPTIONS: dict[str, str] = {
    "guided": "A lines or regional seed, then local search over free coordinates with contact repair, batch moves, depot reseating and adaptive operators.",
    "baseline": "A first-complete spread on a lattice, then greedy shrinking.",
    "regional": "The framework's seeded frontier construction on a clearance map, then shrinking.",
    "climb": "The framework's regional construction, then hill climbing over coordinate moves.",
    "anneal": "The framework's regional construction, then simulated annealing cooled by charged work.",
    "floorplan": "The framework's rows floorplan: items in rows with channels, legalised as a whole structure or not at all; it carries no Endfield rule and lands nothing on the bundled scenarios.",
    "inorder": "The pack's anchors in order, one attempt per cell; the null strategy.",
}
PARALLEL = frozenset({"baseline"})
PARAMETER_TYPES = {
    "int": "int",
    "float": "float",
    "seconds": "float",
    "fraction": "float",
    "bool": "bool",
    "choice": "str",
}
LAYOUT_DEFAULTS: dict[str, Any] = {
    "solver": "guided",
    "seed": 0,
    "seconds": 600.0,
    "max_actions": 0,
    "backend": "auto",
    "frame_every": 100,
    "spread_attempts": 0,
    "workers": 0,
    "solver_options": "{}",
}
LIMITS: dict[str, int] = {"spread_attempts": 4096, "attempts": 4096}
DEFAULT_UNITS = 20_000
ROUTER_COSTS: dict[str, float] = {
    "step": 10,
    "turn": 5,
    "crossing": 40,
    "ripup": 20,
    "displace": 0,
    "detour": 25.0,
    "slack": 400.0,
}
ROUTER_NEGOTIATION: dict[str, Any] = {
    "max_rips": 0,
    "lanes": True,
    "wire_model": "lanes",
    "float_scale": 10,
}


class ConfigurationError(ValueError):
    """A setting the stage does not know, or a value it cannot take."""


LayoutError = ConfigurationError


def settings_of(defaults: dict, values: dict | None = None) -> dict:
    """The defaults overridden by ``values``, each cast to its default's type; unknown names and non-finite or negative numbers refused."""
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


def shipped() -> dict[str, str]:
    """Every registered solver the project or the framework ships by its studio name, the project's first."""
    return {
        solver_id.removeprefix(PREFIX): solver_id
        for solver_id in sorted(known(), key=lambda i: (i not in SOLVER_IDS, i))
        if solver_id in SOLVER_IDS
        or type(get(solver_id)).__module__.startswith(FRAMEWORK)
    }


SOLVER_NAMES = shipped()


def framework_id(name: str) -> str:
    """The framework solver behind a studio name."""
    if name not in SOLVER_NAMES:
        raise ConfigurationError(
            f"unknown solver {name!r}; known: {sorted(SOLVER_NAMES)}"
        )
    return SOLVER_NAMES[name]


def solver_options(params: dict[str, Any]) -> dict[str, Any]:
    """The solver's own params from the ``solver_options`` JSON object."""
    try:
        options = json.loads(params.get("solver_options") or "{}")
    except (ValueError, TypeError) as error:
        raise ConfigurationError("solver_options must be a JSON object") from error
    if not isinstance(options, dict):
        raise ConfigurationError("solver_options must be a JSON object")
    return options


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
    for name in ("spread_attempts", "attempts"):
        if spread and name in declared:
            options.setdefault(name, spread)
            break

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
    """Seconds and actions as given; neither given means ``DEFAULT_UNITS`` actions."""
    seconds = float(params.get("seconds") or 0) or None
    units = int(params.get("max_actions") or 0) or None
    if seconds is None and units is None:
        units = DEFAULT_UNITS
    return Budget(units=units, seconds=seconds)


@dataclass(frozen=True)
class Entry:
    """One studio solver: its name, framework id and declared params."""

    name: str
    solver_id: str

    @property
    def params(self) -> tuple[Any, ...]:
        return get(self.solver_id).params

    @property
    def defaults(self) -> dict[str, Any]:
        return {
            p.name: float(p.default) if isinstance(p.default, Fraction) else p.default
            for p in self.params
        }

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "id": self.solver_id,
            "description": DESCRIPTIONS.get(self.name, ""),
            "defaults": self.defaults,
            "parameter_types": {p.name: PARAMETER_TYPES[p.type] for p in self.params},
            "choices": {p.name: list(p.choices) for p in self.params if p.choices},
            "parallel": self.name in PARALLEL,
        }


class Catalog:
    """The studio's solvers by name."""

    def __init__(self, names: dict[str, str]) -> None:
        self.entries = {
            name: Entry(name, solver_id) for name, solver_id in names.items()
        }

    def get(self, name: str) -> Entry:
        if name not in self.entries:
            raise ConfigurationError(f"unknown solver {name!r}")
        return self.entries[name]

    def describe(self) -> list[dict[str, Any]]:
        return [entry.describe() for entry in self.entries.values()]


SOLVERS = Catalog(SOLVER_NAMES)

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
    "framework_id",
    "router_of",
    "settings_of",
    "shipped",
    "solver_of",
    "solver_options",
    "typed_option",
]
