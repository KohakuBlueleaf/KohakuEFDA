"""Transactions and marks: a journal of undo actions the world records for every mutation."""

from collections.abc import Callable
from typing import Self

from kohakulayout.errors import StateError

Undo = Callable[[], None]


class Transaction:
    """A journal of undo actions. Exiting without ``commit`` rolls everything back."""

    def __init__(self, world: "object") -> None:
        self._world = world
        self._journal: list[Undo] = []
        self.committed = False
        self.open = False

    def record(self, undo: Undo) -> None:
        if not self.open:
            raise StateError("a mutation outside a transaction")
        self._journal.append(undo)

    def mark(self) -> int:
        return len(self._journal)

    def rollback_to(self, mark: int) -> None:
        while len(self._journal) > mark:
            self._journal.pop()()

    def rollback(self) -> None:
        self.rollback_to(0)

    def commit(self) -> None:
        self.committed = True

    def __enter__(self) -> Self:
        self.open = True
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        if exc_type is not None or not self.committed:
            self.rollback()
        self.open = False
        self._journal.clear()
        return False
