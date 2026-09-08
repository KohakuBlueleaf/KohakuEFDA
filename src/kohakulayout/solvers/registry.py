"""The solver registry: solvers by id, a project adds its own without editing the catalog."""

from typing import Any

from kohakulayout.errors import SolverError

_SOLVERS: dict[str, type] = {}


def register(solver: type) -> type:
    _SOLVERS[solver.id] = solver
    return solver


def known() -> tuple[str, ...]:
    return tuple(sorted(_SOLVERS))


def get(solver_id: str, **kwargs: Any) -> Any:
    cls = _SOLVERS.get(solver_id)
    if cls is None:
        raise SolverError(f"no solver {solver_id!r}; known: {list(known())}")
    return cls(**kwargs)


__all__ = ["get", "known", "register"]
