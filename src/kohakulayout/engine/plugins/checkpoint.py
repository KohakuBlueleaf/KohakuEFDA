"""Checkpoint cadence: a checkpoint after every N accepts or every S seconds."""

import time
from typing import Any

from kohakulayout.engine.plugins.protocol import EnginePlugin


class CheckpointPlugin(EnginePlugin):
    name = "checkpoint"
    priority = 70

    def __init__(self, every_accepts: int = 0, every_seconds: float = 0.0) -> None:
        self.every_accepts = every_accepts
        self.every_seconds = every_seconds
        self.accepts = 0
        self.last = time.monotonic()

    def post_accept(self, ctx: Any, token: Any, assessment: Any) -> None:
        self.accepts += 1
        due = self.every_accepts > 0 and self.accepts % self.every_accepts == 0
        if (
            self.every_seconds > 0
            and time.monotonic() - self.last >= self.every_seconds
        ):
            due = True
        if due:
            self.last = time.monotonic()
            ctx.checkpoint()


__all__ = ["CheckpointPlugin"]
