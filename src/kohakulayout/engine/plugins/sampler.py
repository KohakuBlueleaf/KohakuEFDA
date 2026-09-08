"""Frame sampling by cadence: every N frames pass, every M of those carry a layout; the rest are dropped."""

from typing import Any

from kohakulayout.engine.plugins.protocol import DROP, EnginePlugin

KEEP_PHASES = frozenset({"start", "end", "constructed", "checkpoint"})


class FrameSampler(EnginePlugin):
    name = "sampler"
    priority = 20

    def __init__(self, every: int = 1, layout_every: int = 0) -> None:
        self.every = max(1, every)
        self.layout_every = layout_every
        self.seen = 0

    def on_frame(self, ctx: Any, frame: Any) -> Any:
        self.seen += 1
        keep = frame.phase.rsplit("/", 1)[-1] in KEEP_PHASES
        if not keep and self.seen % self.every != 0:
            return DROP
        if (
            frame.layout is not None
            and not keep
            and (self.layout_every <= 0 or self.seen % self.layout_every != 0)
        ):
            return frame.model_copy(update={"layout": None})
        return None


__all__ = ["KEEP_PHASES", "FrameSampler"]
