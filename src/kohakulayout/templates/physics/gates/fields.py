"""Stage 2 for the power variant: every gate needs power, a VDD emitter provides it in a square reach."""

from kohakulayout.ir import Cell
from kohakulayout.physics import Emitter, KindCover, Reach
from kohakulayout.templates.physics.gates.library import BINARY, UNARY, VDD

POWERED = frozenset({*BINARY, *UNARY, "DFF"})
POWER_REACH = 3

VDD_EMITTER = Emitter(
    kind="power",
    footprint=VDD,
    reach=Reach(shape="square", radius=POWER_REACH, partial=True),
    overlap="allowed",
)


class GatesFields(KindCover):
    """Gates need ``power``; IN and OUT do not."""

    def __init__(self) -> None:
        super().__init__((VDD_EMITTER,))

    def needs(self, cell: Cell) -> tuple[str, ...]:
        if cell.footprint in POWERED:
            return ("power", *(n for n in cell.needs if n != "power"))
        return cell.needs


__all__ = ["POWERED", "POWER_REACH", "VDD_EMITTER", "GatesFields"]
