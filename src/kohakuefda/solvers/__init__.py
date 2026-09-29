"""The project's solver on the framework, registered on import as ``endfield.guided``."""

from kohakuefda.solvers.guided import GuidedLayout
from kohakuefda.solvers.search import EndfieldProposals, EndfieldSearch, GuidedSearch

SOLVER_IDS: tuple[str, ...] = (GuidedLayout.id,)

__all__ = [
    "SOLVER_IDS",
    "EndfieldProposals",
    "EndfieldSearch",
    "GuidedLayout",
    "GuidedSearch",
]
