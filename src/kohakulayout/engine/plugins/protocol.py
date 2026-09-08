"""The engine plugin protocol: hooks at the engine's seams; None means unchanged."""

from typing import Any

DROP = object()


class EnginePlugin:
    """Subclass and override the hooks you need; every default returns None."""

    name: str = "plugin"
    priority: int = 50

    def pre_attempt(self, ctx: Any, attempt: Any) -> Any:
        return None

    def post_attempt(self, ctx: Any, attempt: Any, result: Any) -> Any:
        return None

    def pre_assess(self, ctx: Any, digest: str, metrics: dict[str, Any]) -> Any:
        return None

    def post_assess(self, ctx: Any, assessment: Any) -> Any:
        return None

    def pre_accept(self, ctx: Any, token: Any, assessment: Any) -> bool | None:
        return None

    def post_accept(self, ctx: Any, token: Any, assessment: Any) -> None:
        return None

    def on_frame(self, ctx: Any, frame: Any) -> Any:
        return None

    def on_checkpoint(self, ctx: Any, checkpoint: Any) -> None:
        return None

    def on_budget(self, ctx: Any, charge: int) -> None:
        return None


__all__ = ["DROP", "EnginePlugin"]
