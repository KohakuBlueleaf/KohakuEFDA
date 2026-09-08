"""Rules: a pack's verify deck. Each rule yields findings; the framework runs every one after an assess."""

from collections.abc import Callable, Iterable
from typing import Any

from kohakulayout.ir import Finding, Layout

Check = Callable[[Any, Layout, dict[str, Any]], Iterable[Finding]]


class FunctionRule:
    """A rule from a plain function, for packs that do not want a class per rule."""

    def __init__(
        self,
        id: str,
        severity: str,
        check: Check,
        attrs: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.id = id
        self.severity = severity
        self._check = check
        self.attrs = attrs or {}

    def check(
        self, world: Any, layout: Layout, metrics: dict[str, Any]
    ) -> Iterable[Finding]:
        for finding in self._check(world, layout, metrics):
            yield finding.model_copy(
                update={
                    "rule": finding.rule or self.id,
                    "attrs": {**self.attrs, **finding.attrs},
                }
            )


def run_rules(
    rules: tuple[Any, ...], world: Any, layout: Layout, metrics: dict[str, Any]
) -> tuple[Finding, ...]:
    out: list[Finding] = []
    for rule in rules:
        out.extend(rule.check(world, layout, metrics))
    return tuple(out)
