"""Solvers: the protocol, the base solver, the registries, conformance, and the shipped families."""

from kohakulayout.solvers.anchors import ANCHORS, anchors_for
from kohakulayout.solvers.base import BaseSolver
from kohakulayout.solvers.baseline import Baseline
from kohakulayout.solvers.conformance import Report, level3
from kohakulayout.solvers.inorder import InOrder
from kohakulayout.solvers.local import MOVES, Anneal, HillClimb
from kohakulayout.solvers.params import coerce, resolve
from kohakulayout.solvers.protocol import Outcome, Param, Solver
from kohakulayout.solvers.regional import Regional
from kohakulayout.solvers.registry import get, known, register
from kohakulayout.solvers.structural import Floorplan

__all__ = [
    "ANCHORS",
    "MOVES",
    "Anneal",
    "BaseSolver",
    "Baseline",
    "Floorplan",
    "HillClimb",
    "InOrder",
    "Outcome",
    "Param",
    "Regional",
    "Report",
    "Solver",
    "anchors_for",
    "coerce",
    "get",
    "known",
    "level3",
    "register",
    "resolve",
]
