"""The exact slot and its optional occupants.

ortools and highspy each bundle a HiGHS; whichever loads second fails to link, so one
process holds one of them. Nothing loads until an occupant is asked for: ``get`` imports
the one named, ``available`` tries them in the order ``KOHAKULAYOUT_EXACT`` sets (``cpsat``
first by default, or ``milp``), and each registers only when its library still imports.
"""

import os
from importlib import import_module

from kohakulayout.solvers.structural.exact.protocol import (
    EXACT,
    Exact,
    Infeasible,
    get,
    register,
)

PREFERRED = os.environ.get("KOHAKULAYOUT_EXACT", "cpsat")
ORDER = ("milp", "cpsat") if PREFERRED == "milp" else ("cpsat", "milp")


def available() -> dict[str, type]:
    """Every occupant whose library imports, loaded in ``ORDER`` on first call; nothing loads at import time."""
    for name in ORDER:
        if name not in EXACT:
            import_module(f"kohakulayout.solvers.structural.exact.{name}")
    return EXACT


__all__ = [
    "EXACT",
    "ORDER",
    "PREFERRED",
    "Exact",
    "Infeasible",
    "available",
    "get",
    "register",
]
