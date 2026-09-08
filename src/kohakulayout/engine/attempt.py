"""Attempts: one function run inside a transaction, with what it cost and what it refused."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from kohakulayout.ir import Refusal


@dataclass
class Attempt:
    label: str
    fn: Callable[[Any], Any]
    cost: int = 0
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass
class Result:
    attempt: Attempt
    refusal: Refusal | None
    value: Any
    before: int
    after: int
    charged: int

    @property
    def ok(self) -> bool:
        return self.refusal is None


class Block(Exception):
    """Raised by a plugin's ``pre_attempt`` to refuse an attempt before it runs."""

    def __init__(self, refusal: Refusal) -> None:
        super().__init__(refusal.detail)
        self.refusal = refusal


__all__ = ["Attempt", "Block", "Result"]
