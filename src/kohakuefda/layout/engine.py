"""The layout engine: one coupled pass that places and routes together, then finishes.

The engine owns no geometry of its own. It hands the netlist to a ``Site`` — every machine at an
absolute cell on one routing grid — and to a ``Builder``, which constructs the line machine by
machine and then anneals it, every candidate and every move being a placement *and* the routing
it forces. When the square cannot hold the result the engine tries again in a larger area rather
than reporting an overlapping or unrouted layout. What comes back is covered with pylons, cut
into modules, measured and checked.

The cost the builder minimises is the rectangle the line needs plus a weight per wire cell and
per junction (a belt is floor area like a machine is, game-knowledge LOG-11), plus a pull toward
the area's corner and a heavy penalty per group rule still unmet.
"""

import logging
import os
import random
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from concurrent.futures.process import BrokenProcessPool

from kohakuefda.layout.assemble import assemble
from kohakuefda.layout.board import Board, board_of
from kohakuefda.layout.chunk import chunk
from kohakuefda.layout.geometry import machine_footprint, unit_footprint
from kohakuefda.layout.place import Block, catalogue_of
from kohakuefda.layout.search import MIXED, SEARCHES
from kohakuefda.layout.shrink import Shrink
from kohakuefda.layout.site import Site
from kohakuefda.layout.spread import Spread
from kohakuefda.model.cells import Netlist
from kohakuefda.model.control import Cancelled, CancelledError, Observe
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.geometry import rotate_edge
from kohakuefda.model.layout import Cell, Entry, Layout
from kohakuefda.model.plan import Finding
from kohakuefda.route.router import Wire
from kohakuefda.verify.rules.geometry import check_layout

LAYOUT_DEFAULTS: dict[str, int | float | str] = {
    "seed": 0,
    "workers": 0,
    "spread_gap": 0,
    "spread_widest": 6,
    "spread_attempts": 32000,
    "shrink_rounds": 200,
    "spread_slice": 64,
    "search": "mixed",
    "flow_order": "bottom-up",
    "candidate_tries": 12,
    "w_wire": 1.0,
    "w_unit": 2.0,
    "w_pull": 0.25,
    "w_shape": 2.0,
    "w_over": 6.0,
    "w_pylon": 12.0,
    "route_iterations": 30,
    "present_cost": 2.0,
    "present_growth": 1.5,
    "turn_cost": 0.5,
    "bridge_cost": 4.0,
    "history_cost": 1.0,
    "pylon": "power_diffuser_1",
    "entry_sides": "NW",
    "frame_every": 20,
}
log = logging.getLogger(__name__)
DEAL = ("anneal", "evolve", "restart")
AUTO_WORKERS = 16
PRIME = 7919
POLL_SECONDS = 0.2
Rank = tuple[int, int, int, float]


def rank_of(site: Site, board: Board) -> Rank:
    """How good a layout is: everything placed and wired first, then whether it stays inside
    the square the basement really has, then what it costs."""
    x0, y0, x1, y1 = site.bbox()
    over = max(0, x1 - x0 - board.square[0], y1 - y0 - board.square[1])
    return (len(site.unplaced()), len(site.unrouted()), over, site.cost())


def _island(
    dataset: Dataset,
    netlist: Netlist,
    params: dict,
    seed: int,
) -> tuple[bool, tuple[int, int, int, int], int]:
    """One run of the restart search in its own process: whether it came out whole, how good
    it was, and where everything ended up.

    Attempts are independent of one another, so a machine with cores to spare runs several
    searches from different seeds and takes the first that finishes whole rather than waiting
    on one; nothing is shared and nothing is merged.
    """
    board = board_of(dataset, netlist.scenario)
    site = Site(dataset, netlist, board, params)
    spread = Spread(site, params, random.Random(seed))
    whole = spread.run()
    if whole:
        Shrink(site, spread, params).run()
    return whole, spread.score([]), seed


class LayoutError(RuntimeError):
    """A parameter the engine cannot use, or a netlist it cannot lay out at all."""


class EngineResult:
    """Where everything ended up, the pylons, the wires, the layout, the cost and its terms."""

    def __init__(
        self,
        blocks: list[Block],
        pylons: list[Cell],
        entries: list[Entry],
        wires: list[Wire],
        layout: Layout,
        cost: float,
        terms: dict[str, float],
        findings: list[Finding],
        fits: bool,
    ) -> None:
        self.blocks = blocks
        self.pylons = pylons
        self.entries = entries
        self.wires = wires
        self.layout = layout
        self.cost = cost
        self.terms = terms
        self.findings = findings
        self.fits = fits


class Engine:
    """Lays out one netlist; ``run`` builds, improves, covers, measures and checks."""

    def __init__(
        self, dataset: Dataset, netlist: Netlist, board: Board, params: dict
    ) -> None:
        self.dataset = dataset
        self.netlist = netlist
        self.board = board
        self.params = params
        for name in ("spread_gap", "spread_widest"):
            if int(params[name]) < 0:
                raise LayoutError(f"{name} cannot be negative")
        if int(params["spread_widest"]) < int(params["spread_gap"]):
            raise LayoutError("spread_widest cannot be below spread_gap")
        if str(params["search"]) != MIXED and str(params["search"]) not in SEARCHES:
            raise LayoutError(f"unknown search {params['search']!r}")
        self.random = random.Random(int(params["seed"]))
        self.pylon = dataset.pylons[str(params["pylon"])]
        self.findings: list[Finding] = list(board.findings)
        self.site: Site | None = None
        self.spread: Spread | None = None

    # ---- the site the result is read from -------------------------------

    @property
    def blocks(self) -> list[Block]:
        return list(self.site.blocks.values())

    def kinds(self, *constraints: str) -> list[Block]:
        return [b for b in self.blocks if b.constraint in constraints]

    def name_of(self, block: Block) -> str:
        """What to call a block in a message: its machine, or the item an input brings in."""
        machine = self.dataset.machines.get(block.fragment.machine_id)
        if machine is not None:
            return machine.names.en
        pin = next(iter(block.pins.values()), None)
        item = self.dataset.items.get(pin.item_id) if pin is not None else None
        return f"the {item.names.en} input" if item is not None else block.id

    def check(self, cancelled: Cancelled | None) -> None:
        if cancelled is not None and cancelled():
            raise CancelledError("layout cancelled")

    # ---- outside inputs and pylons --------------------------------------

    def entry_of(self, block: Block) -> Entry:
        key = next(iter(block.pins))
        pin = block.pins[key]
        cell, edge = block.pin_world(key)
        return Entry(
            id=block.id,
            item_id=pin.item_id,
            rate=pin.rate,
            x=cell[0],
            y=cell[1],
            edge=rotate_edge(edge, 180),
        )

    # ---- the finished layout --------------------------------------------

    def build_layout(self, pylons: list[Cell]) -> Layout:
        site = self.site
        placed = [b for b in self.kinds("free", "slot", "park") if b.id in site.placed]
        layout = assemble(
            self.dataset,
            placed,
            self.dataset.version.id,
            self.netlist.scenario.basement,
            site.width,
            site.height,
            site.area,
            pylons,
            self.pylon.machine_id,
        )
        layout.entries = [
            self.entry_of(b) for b in self.kinds("edge") if b.id in site.placed
        ]
        return layout

    def _cells(self, layout: Layout) -> tuple[set[Cell], set[Cell]]:
        """Every cell the line occupies: those that must lie in the area (machines, units,
        belts, outside inputs) and the pipe cells, which may cross the ring (LOG-08)."""
        area_cells: set[Cell] = set()
        pipe_cells: set[Cell] = set()
        for placed in layout.machines:
            area_cells.update(machine_footprint(self.dataset, placed))
        for unit in layout.units:
            area_cells.update(unit_footprint(self.dataset, unit))
        for segment in layout.segments:
            (pipe_cells if segment.kind == "pipe" else area_cells).update(segment.cells)
        area_cells.update(e.cell for e in layout.entries)
        return area_cells, pipe_cells

    def terms_of(self, layout: Layout, pylons: list[Cell]) -> dict[str, float]:
        """The rectangle the line needs inside the area (pipe cells out in the ring do not
        count), its empty cells, wire length, pylons and bricks below a full belt."""
        area_cells, pipe_cells = self._cells(layout)
        x0, y0, x1, y1 = self.site.area
        occupied = area_cells | {
            c for c in pipe_cells if x0 <= c[0] < x1 and y0 <= c[1] < y1
        }
        if occupied:
            xs = [c[0] for c in occupied]
            ys = [c[1] for c in occupied]
            width, height = max(xs) - min(xs) + 1, max(ys) - min(ys) + 1
        else:
            width = height = 0
        belt = self.dataset.constants.belt_per_min
        underused = sum(
            1
            for b in self.blocks
            if b.kind in ("depot", "unloader", "loader")
            for p in b.pins.values()
            if p.rate < belt
        )
        return {
            "area": float(width * height),
            "width": float(width),
            "height": float(height),
            "waste": float(width * height - len(occupied)),
            "length": float(sum(len(s.cells) for s in layout.segments)),
            "pylons": float(len(pylons)),
            "bricks_underused": float(underused),
            "junctions": float(self.site.junctions()),
        }

    def fits(self, layout: Layout) -> bool:
        area_cells, pipe_cells = self._cells(layout)
        x0, y0, x1, y1 = self.board.area
        return all(x0 <= x < x1 and y0 <= y < y1 for x, y in area_cells) and all(
            0 <= x < self.site.width and 0 <= y < self.site.height
            for x, y in pipe_cells
        )

    def shortfalls(self, uncovered: list[str]) -> list[Finding]:
        """One finding per machine with nowhere to stand, wire with no path and machine no
        pylon can reach."""
        site = self.site
        out: list[Finding] = []
        for block_id in site.unplaced():
            out.append(
                Finding(
                    rule="layout.unplaced",
                    severity="error",
                    subject=block_id,
                    message=f"no position in the square where {self.name_of(site.blocks[block_id])} could be placed and wired",
                )
            )
        for wire in site.unrouted():
            out.append(
                Finding(
                    rule="layout.unrouted",
                    severity="error",
                    subject=wire.net_id,
                    message=f"no room to route {wire.kind} {wire.id} of {wire.net_id} from {wire.source[0]} to {wire.sink[0]}",
                )
            )
        for block_id in uncovered:
            out.append(
                Finding(
                    rule="layout.uncovered",
                    severity="error",
                    subject=block_id,
                    message=f"no free cell within a pylon's reach of {block_id}",
                )
            )
        return out

    # ---- frames ---------------------------------------------------------

    def catalogue_frame(self) -> dict:
        return {
            "kind": "catalogue",
            "grid": [self.site.width, self.site.height],
            "area": list(self.site.area),
            "slots": [[s.x, s.y, s.side.value] for s in self.board.slots],
            "blocks": catalogue_of(self.blocks),
        }

    def final_frame(
        self, layout: Layout, pylons: list[Cell], terms: dict[str, float], fits: bool
    ) -> dict:
        return {
            "kind": "final",
            "blocks": [
                [b.id, b.x, b.y, b.rotation]
                for b in self.blocks
                if b.id in self.site.placed
            ],
            "pylons": [list(p) for p in pylons],
            "entries": [[e.id, e.x, e.y, e.edge.value] for e in layout.entries],
            "terms": terms,
            "fits": fits,
        }

    # ---- the run --------------------------------------------------------

    def rank(self) -> Rank:
        return rank_of(self.site, self.board)

    def attempt(self, observe: Observe | None, cancelled: Cancelled | None) -> bool:
        """Lay the spread: every machine standing in a square of its own, every lane routed.

        With cores to spare the restart search runs on all of them from different seeds, in
        rounds: every worker takes the same small slice of the attempt budget, the round is
        waited out in full, and the whole layout from the lowest seed wins. Taking whichever
        finished first instead would make the result depend on how the machine was loaded, and
        a run with a seed has to give the same layout every time.
        """
        self.site = Site(self.dataset, self.netlist, self.board, self.params)
        self.spread = Spread(self.site, self.params, self.random)
        if observe is not None:
            observe(self.catalogue_frame())
        self.check(cancelled)
        workers = self.islands()
        if workers <= 1:
            alone = self.searching(self.params, int(self.params["seed"]) * PRIME)
            self.spread = Spread(self.site, alone, self.random)
            return self.spread.run(observe, cancelled)
        budget = int(self.params["spread_attempts"])
        slice_size = max(1, int(self.params["spread_slice"]))
        share = dict(self.params)
        share["spread_attempts"] = slice_size
        self.spread = Spread(self.site, share, self.random)
        seed = int(self.params["seed"])
        pool = ProcessPoolExecutor(max_workers=workers)
        try:
            for start in range(0, max(1, budget), slice_size * workers):
                self.check(cancelled)
                seeds = [
                    seed + (start + index * slice_size) * PRIME
                    for index in range(workers)
                ]
                winner = self.best_of(pool, share, seeds, cancelled)
                if winner is not None:
                    self.spread = Spread(
                        self.site, self.searching(share, winner), random.Random(winner)
                    )
                    return self.spread.run(observe, cancelled)
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
        return False

    def islands(self) -> int:
        """How many searches run at once; ``workers`` 0 asks the machine what it can spare."""
        workers = int(self.params["workers"])
        if workers > 0:
            return workers
        return max(1, min(AUTO_WORKERS, os.process_cpu_count() or 1))

    def searching(self, share: dict, seed: int) -> dict:
        """The parameters one worker gets. Under mixed the searches are dealt out over
        the workers rather than chosen between: none of them wins on every scenario, and the
        cores are already there to run all three."""
        if str(share["search"]) != "mixed":
            return share
        return {**share, "search": DEAL[(seed // PRIME) % len(DEAL)]}

    def best_of(
        self, pool: ProcessPoolExecutor, share: dict, seeds: list[int], cancelled=None
    ) -> int | None:
        """Run one search per seed and give back the lowest seed that came out whole.

        A search is a pure function of its seed and its parameters, so the seed is the whole
        result and the parent repeats it: replaying the positions would not do, because a
        lane's path depends on what was already down when it was routed.
        """
        futures = {
            pool.submit(
                _island, self.dataset, self.netlist, self.searching(share, s), s
            ): s
            for s in seeds
        }
        pending = set(futures)
        winners: list[int] = []
        while pending:
            self.check(cancelled)
            done, pending = wait(
                pending, timeout=POLL_SECONDS, return_when=FIRST_COMPLETED
            )
            for future in done:
                try:
                    whole, rank, seed = future.result()
                except (BrokenProcessPool, OSError, ValueError, RuntimeError) as error:
                    log.warning("a search did not finish", error=str(error))
                    continue
                if whole:
                    winners.append((rank, seed))
        return min(winners)[1] if winners else None

    def run(
        self, observe: Observe | None = None, cancelled: Cancelled | None = None
    ) -> EngineResult:
        """Build and improve; when a round runs out of steps with machines still homeless, try
        again in a larger area with the time that is left, then cover, cut, measure and check.

        A round that ran out of *time* has shown nothing about the square, so it keeps what it
        has instead of spending the rest of the budget on a larger area.
        """
        started = time.monotonic()
        log.info(
            "layout started",
            basement=self.netlist.scenario.basement.basement_id,
            level=self.netlist.scenario.basement.level,
            cells=len(self.netlist.cells),
            nets=len(self.netlist.nets),
            square=f"{self.board.square[0]}x{self.board.square[1]}",
            seed=int(self.params["seed"]),
        )
        if self.attempt(observe, cancelled):
            Shrink(self.site, self.spread, self.params).run()
            if observe is not None:
                observe(self.spread.frame("build"))
        if not self.site.placed:
            raise LayoutError("no layout could be produced")
        pylons, uncovered = self.site.pylons()
        layout = self.build_layout(pylons)
        self.site.router.emit(layout)
        layout.modules = chunk(self.dataset, layout)
        fits = self.fits(layout)
        if fits:
            layout.area = self.board.area
            layout.width, layout.height = self.board.grid
        terms = self.terms_of(layout, pylons)
        findings = list(self.findings) + self.shortfalls(uncovered)
        faults = self.site.faults()
        if faults:
            findings.append(
                Finding(
                    rule="layout.group_faults",
                    severity="error",
                    subject="layout",
                    message=f"{faults} group rule(s) unmet: a brick off its bus, a bus part off the cluster, or a machine outside its gas zone",
                )
            )
        if not fits:
            findings.append(
                Finding(
                    rule="layout.too_big",
                    severity="error",
                    subject=self.netlist.scenario.basement.basement_id,
                    message=f"the line needs {int(terms['width'])}×{int(terms['height'])} cells; the square is {self.board.square[0]}×{self.board.square[1]}",
                )
            )
        findings += [
            f for f in check_layout(self.dataset, layout) if f.severity == "error"
        ]
        log.info(
            "layout done" if fits else "layout done, too big for the square",
            seconds=round(time.monotonic() - started, 1),
            size=f"{int(terms['width'])}x{int(terms['height'])}",
            machines=len(layout.machines) - len(pylons),
            wires=int(terms["length"]),
            units=len(layout.units),
            pylons=len(pylons),
            waste=int(terms["waste"]),
            modules=len(layout.modules),
        )
        for finding in findings:
            log.warning(finding.message, rule=finding.rule, subject=finding.subject)
        if observe is not None:
            observe(self.final_frame(layout, pylons, terms, fits))
        return EngineResult(
            self.blocks,
            pylons,
            list(layout.entries),
            self.site.wires,
            layout,
            terms["area"],
            terms,
            findings,
            fits,
        )
