"""Stage 2 for Endfield: machines that draw power need a pylon's square to touch them (COV-01, COV-02).

The PAC powers nothing by itself (COV-03) and no generation is placed (PWR-05): the only
emitter is the pylon, and the framework's greedy cover puts one down inside the placing
transaction wherever a powered machine lands out of reach.
"""

from kohakuefda.physics.library import PYLON_EMITTER
from kohakulayout.ir import Cell
from kohakulayout.physics import KindCover


class EndfieldFields(KindCover):
    def __init__(self) -> None:
        super().__init__((PYLON_EMITTER,))

    def needs(self, cell: Cell) -> tuple[str, ...]:
        return cell.needs


__all__ = ["EndfieldFields"]
