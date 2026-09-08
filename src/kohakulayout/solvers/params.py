"""Parameter resolution: given values coerced to their declared types, unknown names refused."""

from fractions import Fraction
from typing import Any

from kohakulayout.errors import SolverError
from kohakulayout.solvers.protocol import Param


def coerce(param: Param, value: Any) -> Any:
    kind = param.type
    if kind == "int":
        return int(value)
    if kind in ("float", "seconds"):
        return float(value)
    if kind == "fraction":
        return Fraction(value)
    if kind == "bool":
        if isinstance(value, str):
            return value.lower() in ("1", "true", "yes", "on")
        return bool(value)
    if kind == "choice":
        if value not in param.choices:
            raise SolverError(f"{param.name}: {value!r} is not one of {param.choices}")
        return value
    raise SolverError(f"{param.name}: unknown parameter type {kind!r}")


def resolve(declared: tuple[Param, ...], given: dict[str, Any]) -> dict[str, Any]:
    """Every declared parameter with its given or default value; an undeclared name raises."""
    names = {p.name for p in declared}
    unknown = sorted(set(given) - names)
    if unknown:
        raise SolverError(f"unknown parameter(s) {unknown}; declared: {sorted(names)}")
    out: dict[str, Any] = {}
    for param in declared:
        value = given.get(param.name, param.default)
        out[param.name] = None if value is None else coerce(param, value)
    return out


__all__ = ["coerce", "resolve"]
