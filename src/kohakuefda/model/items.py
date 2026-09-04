"""Items that move through the factory."""

from enum import IntEnum

from kohakuefda.model.base import EfdaModel
from kohakuefda.model.names import Names


class Phase(IntEnum):
    """Physical phase, matching the game's ``phaseType`` codes."""

    SOLID = 1
    LIQUID = 2
    GAS = 4

    @property
    def is_fluid(self) -> bool:
        return self is not Phase.SOLID


class Item(EfdaModel):
    """A factory item: id, names, phase and per-building buffer limit."""

    id: str
    names: Names
    phase: Phase
    buffer_limit: int | None = None
    value: int = 0
    storable: bool = True
