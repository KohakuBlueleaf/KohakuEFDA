"""The engine: what a solver runs in. Context, builder, budget, attempts, assessment, plugins, checkpoints."""

from kohakulayout.engine.assessment import assess, metrics
from kohakulayout.engine.attempt import Attempt, Block, Result
from kohakulayout.engine.budget import Budget
from kohakulayout.engine.builder import Builder
from kohakulayout.engine.checkpoint import Checkpoint
from kohakulayout.engine.context import Context
from kohakulayout.engine.execution import InProcess, ProcessPool, make_execution
from kohakulayout.engine.plugins import EnginePlugin, PluginManager, default_plugins
from kohakulayout.engine.progress import CallbackSink, Event, ListSink, NullSink
from kohakulayout.engine.scopes import Scope
from kohakulayout.engine.workspace import Workspace

__all__ = [
    "Attempt",
    "Block",
    "Budget",
    "Builder",
    "CallbackSink",
    "Checkpoint",
    "Context",
    "EnginePlugin",
    "Event",
    "InProcess",
    "ListSink",
    "NullSink",
    "PluginManager",
    "ProcessPool",
    "Result",
    "Scope",
    "Workspace",
    "assess",
    "default_plugins",
    "make_execution",
    "metrics",
]
