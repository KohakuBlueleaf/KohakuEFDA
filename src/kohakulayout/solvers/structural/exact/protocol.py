"""The exact sub-solver slot: a floorplan of rectangles proven optimal or infeasible; absence is a configuration answer."""

from typing import Any, Protocol, runtime_checkable

from kohakulayout.errors import NotAvailable

Boxes = dict[str, tuple[int, int]]
Placed = dict[str, tuple[int, int]]


class Infeasible(Exception):
    """The region cannot hold the items; a proof, not a refusal."""


@runtime_checkable
class Exact(Protocol):
    id: str

    def solve(
        self, boxes: Boxes, region: tuple[int, int], seconds: float
    ) -> Placed: ...


EXACT: dict[str, type] = {}


def register(occupant: type) -> type:
    EXACT[occupant.id] = occupant
    return occupant


def get(name: str, **kwargs: Any) -> Any:
    cls = EXACT.get(name)
    if cls is None:
        raise NotAvailable(
            f"no exact sub-solver {name!r} is available (known: {sorted(EXACT)}); install ortools for cpsat or highspy for milp, or use exact=none"
        )
    return cls(**kwargs)


__all__ = ["EXACT", "Boxes", "Exact", "Infeasible", "Placed", "get", "register"]
