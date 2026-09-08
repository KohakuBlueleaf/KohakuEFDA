"""The plugin manager: hooks run linearly by priority; a transform replaces, a veto stops, DROP discards."""

from typing import Any

from kohakulayout.engine.plugins.protocol import DROP, EnginePlugin


class PluginManager:
    def __init__(
        self, plugins: tuple[EnginePlugin, ...] | list[EnginePlugin] = ()
    ) -> None:
        self.plugins: list[EnginePlugin] = sorted(
            plugins, key=lambda p: (p.priority, p.name)
        )

    def add(self, plugin: EnginePlugin) -> None:
        self.plugins.append(plugin)
        self.plugins.sort(key=lambda p: (p.priority, p.name))

    def names(self) -> tuple[str, ...]:
        return tuple(p.name for p in self.plugins)

    def transform(self, hook: str, ctx: Any, value: Any, *args: Any) -> Any:
        """Each plugin may replace ``value``; DROP ends the chain and is returned."""
        for plugin in self.plugins:
            out = (
                getattr(plugin, hook)(ctx, value, *args)
                if not args
                else getattr(plugin, hook)(ctx, *args, value)
            )
            if out is DROP:
                return DROP
            if out is not None:
                value = out
        return value

    def first(self, hook: str, ctx: Any, *args: Any) -> Any:
        """The first non-None answer, or None."""
        for plugin in self.plugins:
            out = getattr(plugin, hook)(ctx, *args)
            if out is not None:
                return out
        return None

    def notify(self, hook: str, ctx: Any, *args: Any) -> None:
        for plugin in self.plugins:
            getattr(plugin, hook)(ctx, *args)


__all__ = ["PluginManager"]
