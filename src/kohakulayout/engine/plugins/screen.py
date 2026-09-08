"""Metric screens: cheap tests on the framework metrics before a full assessment is paid for."""

from typing import Any

from kohakulayout.engine.plugins.protocol import EnginePlugin


class AreaBound:
    """Rejects a state whose extent area exceeds ``bound``."""

    id = "area"

    def __init__(self, bound: int) -> None:
        self.bound = bound

    def screen(self, metrics: dict[str, Any]) -> bool:
        return metrics.get("area", 0) <= self.bound


class MissingCount:
    """Rejects a state with more than ``allowed`` unplaced cells."""

    id = "missing"

    def __init__(self, allowed: int = 0) -> None:
        self.allowed = allowed

    def screen(self, metrics: dict[str, Any]) -> bool:
        return metrics.get("missing", 0) <= self.allowed


SCREENS: dict[str, type] = {AreaBound.id: AreaBound, MissingCount.id: MissingCount}


class ScreenPlugin(EnginePlugin):
    name = "screen"
    priority = 30

    def __init__(self, screens: tuple[Any, ...] = ()) -> None:
        self.screens = tuple(screens)
        self.rejected = 0

    def pre_assess(self, ctx: Any, digest: str, metrics: dict[str, Any]) -> Any:
        for screen in self.screens:
            if not screen.screen(metrics):
                self.rejected += 1
                return False
        return None


__all__ = ["SCREENS", "AreaBound", "MissingCount", "ScreenPlugin"]
