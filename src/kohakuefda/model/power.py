"""Power coverage: pylons and the square each one powers.

Facts: game-knowledge COV-01 (pylon reach), COV-05, COV-08.
"""

from kohakuefda.model.base import EfdaModel


class Pylon(EfdaModel):
    """A power facility: cells of coverage beyond its footprint and its cable reach in metres."""

    machine_id: str
    reach: int
    auto_connect_length: float
    auto_connect: bool = False
    covers: bool = True

    def coverage(
        self, x: int, y: int, width: int, depth: int
    ) -> tuple[int, int, int, int]:
        """The square a pylon at ``(x, y)`` with footprint ``width × depth`` powers (COV-01)."""
        return (
            x - self.reach,
            y - self.reach,
            x + width + self.reach,
            y + depth + self.reach,
        )
