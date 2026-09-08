"""The fabric: grid size, layers, carriers and regions. Data a physics pack produces."""

from pydantic import field_validator

from kohakulayout.ir.base import Attrs, Model, Rate, check_attrs, check_id
from kohakulayout.ir.geometry import SIDES, XY, Side


class Rect(Model):
    x: int
    y: int
    w: int
    h: int

    def cells(self) -> frozenset[XY]:
        return frozenset(
            (self.x + i, self.y + j) for j in range(self.h) for i in range(self.w)
        )


def rects_from_cells(cells: frozenset[XY]) -> tuple[Rect, ...]:
    """A canonical rectangle cover: row runs, merged downwards while identical."""
    rows: dict[int, list[int]] = {}
    for x, y in cells:
        rows.setdefault(y, []).append(x)
    runs: list[tuple[int, int, int]] = []
    for y in sorted(rows):
        xs = sorted(rows[y])
        start = prev = xs[0]
        for x in xs[1:]:
            if x != prev + 1:
                runs.append((y, start, prev - start + 1))
                start = x
            prev = x
        runs.append((y, start, prev - start + 1))
    rects: list[Rect] = []
    open_below: dict[tuple[int, int], int] = {}
    for y, x, w in runs:
        index = open_below.get((x, w))
        if index is not None and rects[index].y + rects[index].h == y:
            rects[index] = Rect(x=x, y=rects[index].y, w=w, h=rects[index].h + 1)
        else:
            rects.append(Rect(x=x, y=y, w=w, h=1))
            open_below[(x, w)] = len(rects) - 1
    return tuple(sorted(rects, key=lambda r: (r.y, r.x)))


class Carrier(Model):
    id: str
    layer: str
    capacity: Rate | None = None
    attrs: Attrs = {}


class Region(Model):
    """A named cell set, stored as its canonical rectangle cover."""

    id: str
    rects: tuple[Rect, ...] = ()
    attrs: Attrs = {}

    @field_validator("rects")
    @classmethod
    def _canonical(cls, value: tuple[Rect, ...]) -> tuple[Rect, ...]:
        cells: set[XY] = set()
        for rect in value:
            cells |= rect.cells()
        return rects_from_cells(frozenset(cells))

    @classmethod
    def of(cls, id: str, cells: frozenset[XY], attrs: Attrs | None = None) -> "Region":
        return cls(id=id, rects=rects_from_cells(cells), attrs=attrs or {})

    def cells(self) -> frozenset[XY]:
        out: set[XY] = set()
        for rect in self.rects:
            out |= rect.cells()
        return frozenset(out)


class Fabric(Model):
    width: int
    height: int
    layers: tuple[str, ...] = ("ground",)
    carriers: dict[str, Carrier] = {}
    regions: dict[str, Region] = {}
    entries: tuple[Side, ...] = ()
    attrs: Attrs = {}

    def build_cells(self) -> frozenset[XY]:
        """The ``build`` region, or the whole grid when none was declared."""
        if "build" in self.regions:
            return self.regions["build"].cells()
        return frozenset((x, y) for y in range(self.height) for x in range(self.width))

    def in_grid(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def check(self) -> list[str]:
        problems: list[str] = []
        if self.width < 1 or self.height < 1:
            problems.append("fabric: width and height must be positive")
        if not self.layers or len(set(self.layers)) != len(self.layers):
            problems.append("fabric: layers must be non-empty and unique")
        for cid, carrier in self.carriers.items():
            if cid != carrier.id:
                problems.append(f"fabric: carrier key {cid!r} names {carrier.id!r}")
            problems += check_id(carrier.id, f"carrier {carrier.id}")
            if carrier.layer not in self.layers:
                problems.append(
                    f"carrier {carrier.id}: layer {carrier.layer!r} is not a fabric layer"
                )
            if carrier.capacity is not None and carrier.capacity <= 0:
                problems.append(f"carrier {carrier.id}: capacity must be positive")
            problems += check_attrs(carrier.attrs, f"carrier {carrier.id}")
        for rid, region in self.regions.items():
            if rid != region.id:
                problems.append(f"fabric: region key {rid!r} names {region.id!r}")
            for x, y in region.cells():
                if not self.in_grid(x, y):
                    problems.append(
                        f"region {region.id}: cell ({x},{y}) is outside the grid"
                    )
                    break
            problems += check_attrs(region.attrs, f"region {region.id}")
        if len(set(self.entries)) != len(self.entries):
            problems.append("fabric: entries repeat a side")
        for side in self.entries:
            if side not in SIDES:
                problems.append(f"fabric: entry side {side!r} is not N, E, S or W")
        problems += check_attrs(self.attrs, "fabric")
        return problems
