"""Assessment deduplication: a layout digest already assessed returns its assessment without a rebuild."""

from typing import Any

from kohakulayout.engine.plugins.protocol import EnginePlugin


class DedupPlugin(EnginePlugin):
    name = "dedup"
    priority = 40

    def __init__(self, capacity: int = 4096) -> None:
        self.capacity = capacity
        self.cache: dict[str, Any] = {}
        self.hits = 0

    def pre_assess(self, ctx: Any, digest: str, metrics: dict[str, Any]) -> Any:
        found = self.cache.get(digest)
        if found is not None:
            self.hits += 1
        return found

    def post_assess(self, ctx: Any, assessment: Any) -> Any:
        if len(self.cache) >= self.capacity:
            self.cache.pop(next(iter(self.cache)))
        self.cache[assessment.layout] = assessment
        return None


__all__ = ["DedupPlugin"]
