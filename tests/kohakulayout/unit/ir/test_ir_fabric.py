"""ir/fabric.py: canonical rectangle covers and the fabric checks."""

from kohakulayout.ir import Carrier, Fabric, Rect, Region
from kohakulayout.ir.fabric import rects_from_cells


def test_ring_cover_is_four_rectangles_and_canonical() -> None:
    every = frozenset((x, y) for y in range(5) for x in range(6))
    ring = frozenset(c for c in every if c[0] in (0, 5) or c[1] in (0, 4))
    rects = rects_from_cells(ring)
    assert len(rects) == 4
    region = Region(
        id="ring",
        rects=(
            Rect(x=0, y=0, w=6, h=1),
            Rect(x=0, y=1, w=1, h=3),
            Rect(x=5, y=1, w=1, h=3),
            Rect(x=0, y=4, w=6, h=1),
        ),
    )
    assert region.cells() == ring
    assert Region.of("ring", ring) == region
    assert Region(
        id="r", rects=(Rect(x=0, y=0, w=2, h=1), Rect(x=0, y=1, w=2, h=1))
    ).rects == (
        Rect(x=0, y=0, w=2, h=2),
    )


def test_fabric_check_names_each_problem() -> None:
    fabric = Fabric(
        width=4,
        height=4,
        layers=("ground",),
        carriers={"pipe": Carrier(id="pipe", layer="overhead")},
        regions={"build": Region(id="build", rects=(Rect(x=3, y=3, w=2, h=1),))},
        entries=("W", "W"),
    )
    problems = fabric.check()
    assert any("not a fabric layer" in p for p in problems)
    assert any("outside the grid" in p for p in problems)
    assert any("repeat a side" in p for p in problems)
    assert Fabric(width=3, height=3).check() == []
    assert len(Fabric(width=3, height=3).build_cells()) == 9
