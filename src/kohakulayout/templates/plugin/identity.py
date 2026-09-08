"""The identity plugin: every hook, each returning None, so the chain runs and nothing changes."""

from typing import Any

from kohakulayout.engine.plugins import EnginePlugin


class IdentityPlugin(EnginePlugin):
    name = "identity"
    priority = 50

    def __init__(self) -> None:
        self.calls: dict[str, int] = {}

    def _seen(self, hook: str) -> None:
        self.calls[hook] = self.calls.get(hook, 0) + 1

    def pre_attempt(self, ctx: Any, attempt: Any) -> Any:
        self._seen("pre_attempt")
        return None

    def post_attempt(self, ctx: Any, attempt: Any, result: Any) -> Any:
        self._seen("post_attempt")
        return None

    def pre_assess(self, ctx: Any, digest: str, metrics: dict[str, Any]) -> Any:
        self._seen("pre_assess")
        return None

    def post_assess(self, ctx: Any, assessment: Any) -> Any:
        self._seen("post_assess")
        return None

    def pre_accept(self, ctx: Any, token: Any, assessment: Any) -> bool | None:
        self._seen("pre_accept")
        return None

    def post_accept(self, ctx: Any, token: Any, assessment: Any) -> None:
        self._seen("post_accept")

    def on_frame(self, ctx: Any, frame: Any) -> Any:
        self._seen("on_frame")
        return None

    def on_checkpoint(self, ctx: Any, checkpoint: Any) -> None:
        self._seen("on_checkpoint")

    def on_budget(self, ctx: Any, charge: int) -> None:
        self._seen("on_budget")


__all__ = ["IdentityPlugin"]
