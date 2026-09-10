"""The greedy cover keeps off open attach cells while it can and stands on one rather than leave a need uncovered."""

from kohakulayout.ir.geometry import XY
from kohakulayout.physics.fields import GreedyCover
from kohakulayout.templates.physics.gates.fields import VDD_EMITTER


class _Board:
    """A world that only knows which squares are free, which are open attach cells and where building is allowed."""

    def __init__(self, free: set[XY], attach: set[XY]) -> None:
        self.free = free
        self.attach = attach

    def open_attach_owners(self) -> dict[str, dict[XY, str]]:
        return {"ground": {xy: "pin" for xy in self.attach}}

    def layers_for(self, fp) -> tuple[str, ...]:
        return ("ground",)

    def free_footprint(self, fp, x: int, y: int, rot: int) -> bool:
        return (x, y) in self.free

    def in_build(self, xy: XY) -> bool:
        return True

    def field_coverage(self, kind: str) -> frozenset[XY]:
        return frozenset()


def _spot(free: set[XY], attach: set[XY]) -> XY | None:
    return GreedyCover((VDD_EMITTER,))._spot(
        _Board(free, attach), VDD_EMITTER, ((5, 5),)
    )


def test_a_square_off_the_attach_cells_wins_even_when_farther() -> None:
    assert _spot({(4, 5), (7, 5)}, {(4, 5)}) == (7, 5)


def test_an_attach_cell_is_taken_rather_than_no_cover_at_all() -> None:
    assert _spot({(4, 5), (6, 5)}, {(4, 5), (6, 5)}) == (4, 5)
    assert _spot(set(), set()) is None
