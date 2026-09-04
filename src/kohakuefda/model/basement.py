"""Basements (Core AIC Areas): square size by level, the ring outside it, depot access.

Facts: game-knowledge REG-02, REG-03 (ring), REG-04 (squares), DEP-10 (Wuling bus counts),
DEP-11, DEP-12 (Valley IV fixed bus).
"""

from enum import StrEnum

from kohakuefda.model.base import EfdaModel
from kohakuefda.model.names import Names

DEFAULT_SQUARE = (50, 50)


class Region(StrEnum):
    VALLEY4 = "valley4"
    WULING = "wuling"

    @property
    def domain_id(self) -> str:
        return "domain_1" if self is Region.VALLEY4 else "domain_2"


class BusSegment(EfdaModel):
    """A fixed Depot Bus piece in square coordinates (negative = in the ring): its cells."""

    x: int
    y: int
    width: int
    depth: int

    @property
    def rect(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.x + self.width, self.y + self.depth)


class FixedBus(EfdaModel):
    """Valley IV depot access: the port and the sections unlocked per depot level (DEP-12)."""

    kind: str = "fixed"
    port: BusSegment | None = None
    segments_by_level: dict[int, list[BusSegment]] = {}
    positions_known: bool = False

    def segments(self, level: int) -> list[BusSegment]:
        known = [lv for lv in self.segments_by_level if lv <= level]
        return self.segments_by_level[max(known)] if known else []


class LaidBus(EfdaModel):
    """Wuling depot access: player-laid bus ports and sections, counts per depot level (DEP-10)."""

    kind: str = "laid"
    ports_by_level: dict[int, int] = {}
    sections_by_level: dict[int, int] = {}


class Basement(EfdaModel):
    """A Core AIC Area: region, hub or outpost, square by level, ring depth, depot access."""

    id: str
    names: Names
    region: Region
    hub: bool = False
    square_by_level: dict[int, tuple[int, int] | None] = {}
    ring: int = 0
    depot: FixedBus | LaidBus
    source: str = ""

    def square(self, level: int) -> tuple[int, int] | None:
        return self.square_by_level.get(level)

    def square_or_default(self, level: int) -> tuple[int, int]:
        return self.square(level) or DEFAULT_SQUARE
