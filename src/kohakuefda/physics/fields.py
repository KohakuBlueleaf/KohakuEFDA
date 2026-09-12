"""Stage 2 for Endfield: machines that draw power need a pylon's square to touch them (COV-01, COV-02).

The PAC powers nothing by itself (COV-03) and no generation is placed (PWR-05): the only
emitter is the pylon, laid afresh after every placement by a sweep over the powered
machines. Machines are taken in row order; each joins the first group whose pylon
windows still share a free square, else opens a group of its own, and every group gets
one pylon on the first free square of its window, inside the area (REG-03).
"""

from kohakuefda.physics.fabric import AREA
from kohakuefda.physics.library import (
    POWER,
    PYLON_EMITTER,
    PYLON_FOOTPRINT,
    PYLON_REACH,
    PYLON_SIZE,
)
from kohakulayout.ir import Cell
from kohakulayout.physics import KindCover
from kohakulayout.physics.fields import SquareSweep


class PylonSweep(SquareSweep):
    """The framework's square sweep over the pylon: a 2x2 square reaching five cells, in the area."""

    def __init__(self) -> None:
        super().__init__(POWER, PYLON_FOOTPRINT, PYLON_SIZE, PYLON_REACH, AREA)


class EndfieldFields(KindCover):
    def __init__(self) -> None:
        super().__init__((PYLON_EMITTER,), {POWER: PylonSweep()})

    def needs(self, cell: Cell) -> tuple[str, ...]:
        return cell.needs


__all__ = ["EndfieldFields", "PylonSweep"]
