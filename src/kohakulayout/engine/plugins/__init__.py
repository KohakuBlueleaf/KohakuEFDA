"""Engine plugins: the protocol, the manager and the built-in occupants."""

from kohakulayout.engine.plugins.budget import BudgetPlugin
from kohakulayout.engine.plugins.checkpoint import CheckpointPlugin
from kohakulayout.engine.plugins.dedup import DedupPlugin
from kohakulayout.engine.plugins.manager import PluginManager
from kohakulayout.engine.plugins.protocol import DROP, EnginePlugin
from kohakulayout.engine.plugins.repack import REPACK, RepackPlugin
from kohakulayout.engine.plugins.sampler import FrameSampler
from kohakulayout.engine.plugins.screen import (
    SCREENS,
    AreaBound,
    MissingCount,
    ScreenPlugin,
)


def default_plugins() -> tuple[EnginePlugin, ...]:
    """What every context carries unless told otherwise: budget, sampler, dedup."""
    return (BudgetPlugin(), FrameSampler(), DedupPlugin())


__all__ = [
    "DROP",
    "REPACK",
    "SCREENS",
    "AreaBound",
    "BudgetPlugin",
    "CheckpointPlugin",
    "DedupPlugin",
    "EnginePlugin",
    "FrameSampler",
    "MissingCount",
    "PluginManager",
    "RepackPlugin",
    "ScreenPlugin",
    "default_plugins",
]
