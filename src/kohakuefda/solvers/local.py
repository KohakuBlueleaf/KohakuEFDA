"""Local searches: hill climbing and annealing over the framework's moves, constructing and repairing with the regional search."""

from kohakuefda.solvers.regional import EndfieldSearch
from kohakulayout.solvers import Anneal, HillClimb, register


@register
class EndfieldClimb(HillClimb):
    id = "endfield.climb"
    search = EndfieldSearch


@register
class EndfieldAnneal(Anneal):
    id = "endfield.anneal"
    search = EndfieldSearch


__all__ = ["EndfieldAnneal", "EndfieldClimb"]
