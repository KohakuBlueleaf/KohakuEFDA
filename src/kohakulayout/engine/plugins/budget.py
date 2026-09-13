"""Budget accounting: an attempt is charged its cost before it runs; the builder charges each operation through the context."""

from typing import Any

from kohakulayout.engine.plugins.protocol import EnginePlugin


class BudgetPlugin(EnginePlugin):
    name = "budget"
    priority = 10

    def pre_attempt(self, ctx: Any, attempt: Any) -> Any:
        ctx.charge(attempt.cost)
        return None


__all__ = ["BudgetPlugin"]
