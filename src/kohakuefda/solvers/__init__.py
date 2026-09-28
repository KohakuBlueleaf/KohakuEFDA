"""KohakuEFDA-kl's own solvers on the framework: the regional construction, the local searches over it and the rows floorplan, registered as ``endfield.*``."""

from kohakuefda.solvers.lines import EndfieldLines, EndfieldLinesPlan
from kohakuefda.solvers.local import EndfieldAnneal, EndfieldClimb
from kohakuefda.solvers.regional import (
    DEFAULTS,
    EndfieldProposals,
    EndfieldRegional,
    EndfieldSearch,
)
from kohakuefda.solvers.rows import EndfieldFloorplan, EndfieldRows

SOLVER_IDS: tuple[str, ...] = (
    EndfieldRegional.id,
    EndfieldClimb.id,
    EndfieldAnneal.id,
    EndfieldFloorplan.id,
    EndfieldLinesPlan.id,
)

__all__ = [
    "DEFAULTS",
    "SOLVER_IDS",
    "EndfieldAnneal",
    "EndfieldClimb",
    "EndfieldFloorplan",
    "EndfieldLines",
    "EndfieldLinesPlan",
    "EndfieldProposals",
    "EndfieldRegional",
    "EndfieldRows",
    "EndfieldSearch",
]
