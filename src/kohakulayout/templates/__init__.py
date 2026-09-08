"""The framework's own packs and skeletons, each with its test. Importing this registers the packs."""

from kohakulayout.templates.physics.gates import GatesPhysics, GatesPowerPhysics
from kohakulayout.templates.physics.null import NullPhysics
from kohakulayout.templates.plugin import IdentityPlugin
from kohakulayout.templates.solver import Skeleton

__all__ = [
    "GatesPhysics",
    "GatesPowerPhysics",
    "IdentityPlugin",
    "NullPhysics",
    "Skeleton",
]
