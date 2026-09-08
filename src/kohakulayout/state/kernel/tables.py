"""Sharing and crossing tables built once from the physics hooks, so the kernels never see a pack."""

from typing import Any

from kohakulayout.physics.protocol import Occupant


class ShareTable:
    """Memoised ``may_share`` over occupant keys; the native kernel receives the same pairs."""

    def __init__(self, carriers: Any) -> None:
        self._carriers = carriers
        self._cache: dict[tuple[str, str], bool] = {}

    def may_share(self, a: Occupant, b: Occupant) -> bool:
        key = (a.key(), b.key())
        if key not in self._cache:
            self._cache[key] = bool(self._carriers.may_share(a, b))
            self._cache[(key[1], key[0])] = self._cache[key]
        return self._cache[key]

    def pairs(self) -> tuple[tuple[str, str, bool], ...]:
        return tuple(sorted((a, b, v) for (a, b), v in self._cache.items()))
