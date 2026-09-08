"""The exact slot and its optional occupants.

ortools and highspy each bundle a HiGHS; whichever loads second fails to link, so one
process holds one of them. ``KOHAKULAYOUT_EXACT`` names the occupant to load first
(``cpsat`` by default, or ``milp``); the other registers only when its library still imports.
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
for _name in ORDER:
    import_module(f"kohakulayout.solvers.structural.exact.{_name}")

__all__ = ["EXACT", "ORDER", "PREFERRED", "Exact", "Infeasible", "get", "register"]
