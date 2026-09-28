"""Units laid out once, hard: each top-level tile's problem solved on a box of its own with
the project's solvers over several seeds, the best complete and valid layout kept as the
module's macro; the box grows when nothing lands."""

import logging
import math
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from kohakuefda.layout.settings import router_of, solver_of
from kohakuefda.model.basement import Region
from kohakuefda.model.layout import Layout, Placed, Segment, Unit
from kohakuefda.model.scenario import BasementRef
from kohakuefda.physics.boundaries import RIM
from kohakuefda.physics.facts import facts
from kohakuefda.physics.library import BELT, PIPE
from kohakuefda.physics.objective import EndfieldObjective
from kohakuefda.synth.tiles import TileError, macro_of, tile_problem, with_macros
from kohakuefda.verify.complexity import Complexity, complexity
from kohakulayout.engine import Budget
from kohakulayout.ir import Assessment, Netlist, Problem
from kohakulayout.ir import Layout as FrameworkLayout
from kohakulayout.ir.geometry import footprint_cells, rotate_size
from kohakulayout.ir.netlist import Macro
from kohakulayout.pipeline import solve

log = logging.getLogger(__name__)
SEEDS: tuple[int, ...] = (0, 1, 2, 3)
UNITS = 6000
SECONDS = 20.0
SOLVER = "hc"
GAP = 2
GROWTH = 1.3
TRIES = 5
SHRINK = 0.85
SHRINK_STEP = 4
HEIGHT = 3
SQUARE = 2.0
SHRINK_SEEDS: tuple[int, ...] = (0, 1)


@dataclass
class TileResult:
    module_id: str
    problem: Problem
    layout: FrameworkLayout
    assessment: Assessment
    macro: Macro
    seed: int

    @property
    def complexity(self) -> Complexity:
        return tile_complexity(self.problem, self.macro.layout)


def tile_complexity(problem: Problem, layout: FrameworkLayout) -> Complexity:
    """The build complexity of a tile's fragment: its wires, junctions, bridges and kinds."""
    segments = [
        Segment(
            id=f"{net}:{i}",
            kind=BELT if s.carrier == BELT else PIPE,
            cells=list(s.cells),
        )
        for net, w in layout.wires.items()
        for i, s in enumerate(w.segments)
    ]
    units = [
        Unit(id=k, unit_id=u.footprint, x=u.x, y=u.y) for k, u in layout.units.items()
    ]
    machines = [
        Placed(id=k, machine_id=problem.netlist.cells[k].footprint or "", x=p.x, y=p.y)
        for k, p in layout.placements.items()
    ]
    basement = BasementRef(region=Region.VALLEY4, basement_id="tile", level=1)
    width = problem.fabric.width
    height = problem.fabric.height
    stand_in = Layout(
        dataset_version="tile",
        basement=basement,
        width=width,
        height=height,
        machines=machines,
        units=units,
        segments=segments,
    )
    return complexity(stand_in)


def text_map(problem: Problem, layout: FrameworkLayout, footprint: Any) -> str:
    """The fragment as text: machines by their first letter, belts ``=``, pipes ``+``, units ``*``."""
    occupied: dict[tuple[int, int], str] = {}
    for cell_id, p in layout.placements.items():
        fp = problem.netlist.footprint_for(cell_id)
        if fp is None:
            continue
        for xy in footprint_cells(p.x, p.y, fp.width, fp.height, p.rot):
            occupied[xy] = cell_id.split("_", 1)[-1][:1].upper()
    for wire in layout.wires.values():
        for segment in wire.segments:
            for xy in segment.cells:
                occupied.setdefault(xy, "+" if segment.carrier == PIPE else "=")
    for unit in layout.units.values():
        occupied[unit.x, unit.y] = "*"
    rows = []
    for y in range(-1, footprint.height + 1):
        rows.append(
            "".join(occupied.get((x, y), ".") for x in range(-1, footprint.width + 1))
        )
    return "\n".join(rows)


def levels(hier: Netlist, module_id: str) -> list[list[str]]:
    """The body's cells by stage: the longest chain of inner nets from a cell nothing inside feeds."""
    body = hier.modules[module_id].body
    feeders: dict[str, set[str]] = {c: set() for c in body.cells}
    for net in body.nets.values():
        for source in net.sources:
            for sink in net.sinks:
                if source.cell != sink.cell:
                    feeders[sink.cell].add(source.cell)
    stage: dict[str, int] = {}

    def depth(cell: str, seen: frozenset[str]) -> int:
        if cell in stage:
            return stage[cell]
        back = [f for f in feeders[cell] if f not in seen]
        stage[cell] = max((depth(f, seen | {cell}) + 1 for f in back), default=0)
        return stage[cell]

    for cell in body.cells:
        depth(cell, frozenset())
    out: list[list[str]] = [[] for _ in range(max(stage.values(), default=0) + 1)]
    for cell, level in stage.items():
        out[level].append(cell)
    return out


def tile_box(hier: Netlist, module_id: str) -> tuple[int, int]:
    """A first box for the module: its cells in stage rows with a gap of ``GAP`` between
    cells and between rows, or a square holding ``SQUARE`` times the cells' area when the
    rows would be taller than wide (a loop or a fan makes a mesh, not a column), never
    narrower than its widest cell or shorter than its tallest."""
    library = hier.library
    body = hier.modules[module_id].body

    def size(cell_id: str) -> tuple[int, int]:
        fp = library.get(body.cells[cell_id].footprint or "")
        return (fp.width, fp.height) if fp is not None else (1, 1)

    rows = levels(hier, module_id)
    width = max(
        (sum(size(c)[0] for c in row) + GAP * (len(row) - 1) for row in rows if row),
        default=1,
    )
    height = sum(max(size(c)[1] for c in row) for row in rows if row) + GAP * (
        len(rows) - 1
    )
    if height > width:
        side = math.ceil(
            math.sqrt(SQUARE * sum(w * h for w, h in map(size, body.cells)))
        )
        width = height = side
    widest = max((size(c)[0] for c in body.cells), default=1)
    tallest = max((size(c)[1] for c in body.cells), default=1)
    return (max(width, widest) + 2 * GAP, max(height, tallest) + 2 * GAP)


def pinned_extent(problem: Problem) -> tuple[int | None, int | None]:
    """The width a cell on both the west and east rims fixes, the height one on north and south fixes."""
    width = height = None
    for cell_id, cell in problem.netlist.cells.items():
        if cell.constraint.kind != RIM:
            continue
        sides = {str(r).split(":")[0] for r in facts(cell).get("rims", ())}
        fp = problem.netlist.footprint_for(cell_id)
        if fp is None:
            continue
        w, h = rotate_size(fp.width, fp.height, 0)
        if {"W", "E"} <= sides:
            width = w
        if {"N", "S"} <= sides:
            height = h
    return width, height


def cost_of(assessment: Assessment) -> Fraction:
    """The pack's weighted sum of the assessment's metrics, plus ``HEIGHT`` per row of
    extent: rows of units are as tall as their tallest unit, so a wide unit beats a tall one.
    """
    weights = EndfieldObjective.weights
    return sum(
        (Fraction(assessment.metrics.get(k, 0)) * w for k, w in weights.items()),
        Fraction(0),
    ) + HEIGHT * Fraction(assessment.metrics.get("extent_h", 0))


def solve_tile(
    problem: Problem, seeds: tuple[int, ...] = SEEDS, units: int = UNITS
) -> tuple[FrameworkLayout, Assessment, int] | None:
    """The best complete, valid layout over the seeds by the pack's cost, or None."""
    solver_id, options = solver_of({"solver": SOLVER, "solver_options": "{}"})
    best: tuple[FrameworkLayout, Assessment, int] | None = None
    for seed in seeds:
        result = solve(
            problem,
            solver=solver_id,
            seed=seed,
            budget=Budget(units=units, seconds=SECONDS),
            params=options,
            router=router_of(),
            kernel="auto",
        )
        found = result.assessment
        if result.layout is None or not (found.complete and found.valid):
            continue
        if best is None or cost_of(found) < cost_of(best[1]):
            best = (result.layout, found, seed)
    return best


def attempt(
    hier: Netlist,
    module_id: str,
    box: tuple[int, int],
    seeds: tuple[int, ...],
    units: int,
) -> TileResult | None:
    """The module solved on ``box`` and made a macro, or None."""
    problem = tile_problem(hier, module_id, box)
    fixed_w, fixed_h = pinned_extent(problem)
    if fixed_w is not None or fixed_h is not None:
        box = (fixed_w or box[0], fixed_h or box[1])
        problem = tile_problem(hier, module_id, box)
    found = solve_tile(problem, seeds, units)
    if found is None:
        return None
    layout, assessment, seed = found
    try:
        macro = macro_of(hier, module_id, problem, layout)
    except TileError as failure:
        log.info("tile %s on %dx%d: %s", module_id, box[0], box[1], failure)
        return None
    return TileResult(module_id, problem, layout, assessment, macro, seed)


def lay_out_tile(
    hier: Netlist, module_id: str, seeds: tuple[int, ...] = SEEDS, units: int = UNITS
) -> TileResult:
    """The module solved on a growing box until a macro derives, then on shrinking boxes
    while one still does, the height first; ``TileError`` when no box lands."""
    width, height = tile_box(hier, module_id)
    result = None
    for _ in range(TRIES):
        result = attempt(hier, module_id, (width, height), seeds, units)
        if result is not None:
            break
        width, height = math.ceil(width * GROWTH), math.ceil(height * GROWTH)
    if result is None:
        raise TileError(f"{module_id}: no complete layout in {TRIES} boxes")
    for axis in (1, 0):
        while True:
            box = [int(v) for v in result.problem.params["square"]]
            box[axis] = max(math.floor(box[axis] * SHRINK), box[axis] - SHRINK_STEP)
            if box[axis] < 3:
                break
            smaller = attempt(hier, module_id, (box[0], box[1]), SHRINK_SEEDS, units)
            if smaller is None or cost_of(smaller.assessment) >= cost_of(
                result.assessment
            ):
                break
            result = smaller
    log.info(
        "tile %s laid out on %dx%d (seed %d, cost %s)",
        module_id,
        result.macro.footprint.width if result.macro.footprint else 0,
        result.macro.footprint.height if result.macro.footprint else 0,
        result.seed,
        cost_of(result.assessment),
    )
    return result


def lay_out_tiles(
    hier: Netlist, seeds: tuple[int, ...] = SEEDS, units: int = UNITS
) -> tuple[Netlist, dict[str, TileResult]]:
    """Every module laid out; the hierarchical netlist with its instances on the macros."""
    results = {m: lay_out_tile(hier, m, seeds, units) for m in sorted(hier.modules)}
    return with_macros(hier, {m: r.macro for m, r in results.items()}), results


__all__ = [
    "SECONDS",
    "SEEDS",
    "UNITS",
    "TileResult",
    "attempt",
    "cost_of",
    "lay_out_tile",
    "lay_out_tiles",
    "levels",
    "pinned_extent",
    "solve_tile",
    "text_map",
    "tile_box",
    "tile_complexity",
]
