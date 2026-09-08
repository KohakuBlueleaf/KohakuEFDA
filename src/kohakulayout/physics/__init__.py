"""The physics protocol: how a project states its game, and the defaults every hook has."""

from kohakulayout.physics.base import BasePhysics
from kohakulayout.physics.boundaries import DefaultBoundaries, edge_cells, free_anchors
from kohakulayout.physics.carriers import DefaultCarriers
from kohakulayout.physics.diagnose import diagnose
from kohakulayout.physics.fields import (
    DefaultFields,
    GreedyCover,
    KindCover,
    reach_cells,
    satisfied,
)
from kohakulayout.physics.flow import DefaultFlow
from kohakulayout.physics.objective import DefaultObjective, energy
from kohakulayout.physics.protocol import (
    Anchor,
    Boundaries,
    Carriers,
    CrossingRule,
    Emitter,
    Fields,
    Flow,
    JunctionRule,
    Objective,
    Occupant,
    Physics,
    Reach,
    Rule,
    UnitPlacement,
)
from kohakulayout.physics.registry import (
    discover,
    get,
    known,
    locate,
    path_of,
    register,
)
from kohakulayout.physics.rules import FunctionRule, run_rules

__all__ = [
    "Anchor",
    "BasePhysics",
    "Boundaries",
    "Carriers",
    "CrossingRule",
    "DefaultBoundaries",
    "DefaultCarriers",
    "DefaultFields",
    "DefaultFlow",
    "DefaultObjective",
    "Emitter",
    "Fields",
    "Flow",
    "FunctionRule",
    "GreedyCover",
    "JunctionRule",
    "KindCover",
    "Objective",
    "Occupant",
    "Physics",
    "Reach",
    "Rule",
    "UnitPlacement",
    "diagnose",
    "discover",
    "edge_cells",
    "energy",
    "free_anchors",
    "get",
    "known",
    "locate",
    "path_of",
    "reach_cells",
    "register",
    "run_rules",
    "satisfied",
]
