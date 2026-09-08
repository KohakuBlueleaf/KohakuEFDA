"""Repack cadence: after every N accepts a registered repack action runs through the builder."""

from collections.abc import Callable
from typing import Any

from kohakulayout.engine.plugins.protocol import EnginePlugin

RepackAction = Callable[[Any], None]


def identity(builder: Any) -> None:
    return None


REPACK: dict[str, RepackAction] = {"identity": identity}


class RepackPlugin(EnginePlugin):
    name = "repack"
    priority = 60

    def __init__(self, every: int = 0, action: str = "identity") -> None:
        self.every = every
        self.action = action
        self.accepts = 0
        self.runs = 0

    def post_accept(self, ctx: Any, token: Any, assessment: Any) -> None:
        self.accepts += 1
        if self.every > 0 and self.accepts % self.every == 0:
            self.runs += 1
            REPACK[self.action](ctx.builder())


__all__ = ["REPACK", "RepackAction", "RepackPlugin", "identity"]
