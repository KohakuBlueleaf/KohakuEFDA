"""KohakuEFDA-kl's own solvers on the framework: the regional construction and the local searches over it, registered as ``endfield.*``."""

from kohakuefda.solvers.local import EndfieldAnneal, EndfieldClimb
from kohakuefda.solvers.regional import (
    DEFAULTS,
    EndfieldProposals,
    EndfieldRegional,
    EndfieldSearch,
)

SOLVER_IDS: tuple[str, ...] = (
    EndfieldRegional.id,
    EndfieldClimb.id,
    EndfieldAnneal.id,
)

__all__ = [
    "DEFAULTS",
    "SOLVER_IDS",
    "EndfieldAnneal",
    "EndfieldClimb",
    "EndfieldProposals",
    "EndfieldRegional",
    "EndfieldSearch",
]
