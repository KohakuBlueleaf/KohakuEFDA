"""The layout stage's settings and its solver table: the project's names for the framework's solvers.

The studio and the CLI keep their flat settings (``solver``, ``seed``, ``seconds``,
``max_actions``, ``backend``, ``solver_options``); this module maps them onto a framework
solver id, its params and a budget. The catalogue the studio lists is the framework's,
described from each solver's declared params under the project's legacy names.
"""

import json
import math
from typing import Any

from kohakuefda.layout.config import Catalog, ConfigurationError, Entry, settings_of
from kohakulayout.engine import Budget
from kohakulayout.errors import SolverError
from kohakulayout.solvers import get, known
from kohakulayout.solvers.params import resolve

SOLVER_NAMES: dict[str, str] = {
    "hc": "climb",
    "sa": "anneal",
    "baseline": "baseline",
    "regional": "regional",
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
    "frame_every": 8,
    "spread_attempts": 0,
    "workers": 0,
    "solver_options": "{}",
}
LayoutError = ConfigurationError
DEFAULT_UNITS = 20_000


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
    "SOLVERS",
    "SOLVER_NAMES",
    "LayoutError",
    "budget_of",
    "catalogue",
    "framework_id",
    "settings_of",
    "solver_of",
    "solver_options",
    "typed_option",
]
