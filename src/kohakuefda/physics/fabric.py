"""The Endfield fabric: the Core AIC Area in the middle of its ring, two layers, belts and pipes.

The grid is the square plus the ring on every side (REG-02, REG-03). Belts run on the
ground at 30/min, pipes overhead at 120/min (LOG-01, LOG-02). Regions: ``build`` and ``area`` are
the square, ``ring`` what is left, ``bus_fixed`` the cells a Valley IV
bus occupies (DEP-12). The brick slots (``x:y:side``), the fixed cells (``x:y``) and the
entry border ride in the params and the fabric's attrs as flat text.
"""

from fractions import Fraction
from typing import Any

from kohakuefda.physics.library import BELT, GROUND, PIPE, SKY
from kohakulayout.ir import Carrier, Fabric, Region
from kohakulayout.ir.geometry import XY

BELT_PER_MIN = Fraction(30)
PIPE_PER_MIN = Fraction(120)
BUILD = "build"
AREA = "area"
RING = "ring"
FIXED = "bus_fixed"
NAMESPACE = "endfield"
Rect = tuple[int, int, int, int]
Slot = tuple[int, int, str]


def fabric(params: dict[str, Any]) -> Fabric:
    """The fabric of one basement: ``square``, ``ring``, ``fixed`` cells, ``slots``, ``entry_area``."""
    sw, sh = (int(v) for v in params["square"])
    ring = int(params.get("ring", 0))
    width, height = sw + 2 * ring, sh + 2 * ring
    every = frozenset((x, y) for y in range(height) for x in range(width))
    area = frozenset(
        (x, y) for y in range(ring, ring + sh) for x in range(ring, ring + sw)
    )
    fixed = frozenset(cell_of(text) for text in params.get("fixed", ()))
    regions = {BUILD: Region.of(BUILD, area), AREA: Region.of(AREA, area)}
    if every - area:
        regions[RING] = Region.of(RING, every - area)
    if fixed:
        regions[FIXED] = Region.of(FIXED, fixed)
    entry = params.get("entry_area") or [ring, ring, ring + sw, ring + sh]
    return Fabric(
        width=width,
        height=height,
        layers=(GROUND, SKY),
        carriers={
            BELT: Carrier(id=BELT, layer=GROUND, capacity=BELT_PER_MIN),
            PIPE: Carrier(id=PIPE, layer=SKY, capacity=PIPE_PER_MIN),
        },
        regions=regions,
        entries=("N", "E", "S", "W"),
        attrs={
            NAMESPACE: {
                "square": [sw, sh],
                "ring": ring,
                "slots": [str(text) for text in params.get("slots", ())],
                "entry_area": [int(v) for v in entry],
                "facts": ["LOG-01", "LOG-02", "REG-02", "REG-03", "DEP-12"],
            }
        },
    )


def cell_of(text: str) -> XY:
    x, y = str(text).split(":")
    return (int(x), int(y))


def slot_of(text: str) -> Slot:
    x, y, side = str(text).split(":")
    return (int(x), int(y), side)


def facts_of(fabric: Fabric) -> dict[str, Any]:
    return fabric.attrs.get(NAMESPACE, {})


def area_rect(fabric: Fabric) -> Rect:
    """The Core AIC Area as ``(x0, y0, x1, y1)``, exclusive on the far side."""
    info = facts_of(fabric)
    ring = int(info.get("ring", 0))
    sw, sh = (int(v) for v in info.get("square", (fabric.width, fabric.height)))
    return (ring, ring, ring + sw, ring + sh)


def entry_rect(fabric: Fabric) -> Rect:
    """Where outside inputs may stand: the entry area, else the Core AIC Area."""
    entry = facts_of(fabric).get("entry_area")
    if entry is None:
        return area_rect(fabric)
    x0, y0, x1, y1 = (int(v) for v in entry)
    return (x0, y0, x1, y1)


def slots_of(fabric: Fabric) -> tuple[Slot, ...]:
    return tuple(slot_of(text) for text in facts_of(fabric).get("slots", ()))


def fixed_cells(fabric: Fabric) -> frozenset[XY]:
    region = fabric.regions.get(FIXED)
    return region.cells() if region is not None else frozenset()


__all__ = [
    "AREA",
    "BELT_PER_MIN",
    "BUILD",
    "FIXED",
    "NAMESPACE",
    "PIPE_PER_MIN",
    "RING",
    "Rect",
    "Slot",
    "area_rect",
    "cell_of",
    "entry_rect",
    "fabric",
    "facts_of",
    "fixed_cells",
    "slot_of",
    "slots_of",
]
