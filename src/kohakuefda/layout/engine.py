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
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool

from kohakuefda.layout.assemble import assemble
from kohakuefda.layout.board import Board, board_of
from kohakuefda.layout.chunk import chunk
from kohakuefda.layout.geometry import machine_footprint, unit_footprint
from kohakuefda.layout.heuristic import engine as heuristic
from kohakuefda.layout.place import Block, catalogue_of
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
from kohakuefda.util.progress import Ticker
from kohakuefda.verify.rules.geometry import check_layout

LAYOUT_DEFAULTS: dict[str, int | float | str] = {
    "seed": 0,
    "workers": 0,
    "restarts": 8,
    "spread_gap": 0,
    "spread_widest": 6,
    "shrink_rounds": 200,
    "shrink_walk": 600,
    "shrink_heat": 6.0,
    "shrink_spin": 0.25,
    "heuristic": "anneal",
    "native": "on",
    "start": "scatter",
    "seed_attempts": 1500,
    "seed_draws": 8,
    "build_tries": 8,
    "route_rounds": 6,
    "repair_tries": 4,
    "route_widest": 0,
    "sa_moves": 200000,
    "sa_schedule": "adaptive",
    "sa_start_temperature": 0.0,
    "sa_end_temperature": 0.0001,
    "sa_accept_initial": 0.9,
    "sa_target_accept": 0.44,
    "sa_range_start": 0.5,
    "sa_range_floor": 1,
    "sa_warmup": 200,
    "sa_window": 100,
    "sa_polish": 8000,
    "sa_polish_overlap": 128.0,
    "sa_reheat": 3,
    "sa_reheat_after": 20000,
    "sa_fast_c": 100.0,
    "sa_fast_k": 7,
    "ga_population": 24,
    "ga_generations": 200,
    "ga_crossover": 0.9,
    "ga_mutation": 0.3,
    "ga_tournament": 3,
    "ga_elitism": 2,
    "ga_local_moves": 200,
    "move_displace": 6.0,
    "move_swap": 3.0,
    "move_rotate": 2.0,
    "move_shift": 1.0,
    "w_area": 1.0,
    "w_overlap": 8.0,
    "w_group": 8.0,
    "w_shut": 8.0,
    "w_crowd": 1.0,
    "w_tight": 4.0,
    "w_jam": 0.0,
    "route_slack": 1.5,
    "route_slacks": "1.1",
    "route_heat": 0.25,
    "route_cool": 0.5,
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


def _restart(
    dataset: Dataset,
    netlist: Netlist,
    params: dict,
    seed: int,
    anchors: dict,
) -> tuple[tuple[int, int, int, int], int]:
    """One walk from one seed, in its own process: what it came to, and the seed.

    The spread is deterministic, so every restart would lay exactly the same one; it is laid
    once by the parent and handed here as anchors instead, and only the walk -- which is where
    the variance is, a fifth of the area between seeds on the same factory -- is repeated.
    Only the seed comes back, because the parent can replay it and wants the frames.
    """
    board = board_of(dataset, netlist.scenario)
    site = Site(dataset, netlist, board, params)
    settings = {**params, "seed": seed, "restarts": 1}
    if not heuristic.run(site, settings, random.Random(seed), None, None, anchors):
        return (len(netlist.cells), 0, 1 << 30, 1 << 30), seed
    spread = Spread(site, settings, random.Random(seed))
    spread.laid = list(site.placed)
    Shrink(site, spread, settings).run()
    x0, y0, x1, y1 = site.bbox()
    return (
        len(site.unplaced()),
        len(site.unrouted()),
        (x1 - x0) * (y1 - y0),
        site.wire_cells(),
    ), seed


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

        One pass, in this process. The spread is constructive: a machine goes into a square
        with room round it and its lanes are routed where it stands, so there is nothing to
        search and nothing to hand to another core. Spreading the same lattice over shuffled
        orders on sixteen cores took longer in wall time than one pass takes, for a layout the
        placement walk improves on anyway.
        """
        self.site = Site(self.dataset, self.netlist, self.board, self.params)
        self.spread = Spread(self.site, self.params, self.random)
        if observe is not None:
            observe(self.catalogue_frame())
        self.check(cancelled)
        return self.spread.run(observe, cancelled)

    def luckiest(self, anchors: dict, cancelled: Cancelled | None) -> int:
        """The seed that lays out best, found by trying several at once.

        The walk over placements finishes a fifth apart on the same factory depending on where
        it started, and more moves do not close that -- restarts do. They are independent, so
        the cores that ran them are the whole win: eight seeds cost one seed's wall time, and
        the layout that comes back is the best of them rather than the first.

        Only the winning seed comes back; the parent lays it out again itself, so a watcher
        sees a run being built rather than a result appearing.
        """
        wanted = max(1, int(self.params.get("restarts", 1)))
        seed = int(self.params["seed"])
        if wanted <= 1 or str(self.params["heuristic"]) == "off":
            return seed
        seeds = [seed + index * PRIME for index in range(wanted)]
        ticker = Ticker(len(seeds), "restarts")
        best: tuple | None = None
        done = 0
        with ProcessPoolExecutor(max_workers=min(wanted, self.islands())) as pool:
            futures = {
                pool.submit(
                    _restart, self.dataset, self.netlist, self.params, s, anchors
                ): s
                for s in seeds
            }
            for future in as_completed(futures):
                self.check(cancelled)
                done += 1
                try:
                    score, got = future.result()
                except (BrokenProcessPool, OSError, ValueError, RuntimeError) as error:
                    log.warning("a restart did not finish", error=str(error))
                    continue
                if best is None or (score, got) < best:
                    best = (score, got)
                ticker.tick(done, f"best area {best[0][2]}")
        ticker.done()
        if best is None:
            return seed
        log.info("restarts done", tried=len(seeds), seed=best[1], area=best[0][2])
        return best[1]

    def islands(self) -> int:
        """How many searches run at once; ``workers`` 0 asks the machine what it can spare."""
        workers = int(self.params["workers"])
        if workers > 0:
            return workers
        return max(1, min(AUTO_WORKERS, os.process_cpu_count() or 1))

    def contend(self, observe: Observe | None, cancelled: Cancelled | None) -> None:
        """Let the heuristic placer try the same netlist and keep whichever did better.

        The two search different things — one arranges a lattice, the other walks placements —
        and neither wins everywhere, so they run beside each other and the smaller answer is
        the one returned. A heuristic layout that is not whole never counts, so this can only
        improve on what the constructive pass built.
        """
        if str(self.params["heuristic"]) == "off":
            return
        mine = self.measure(self.site)
        other = Site(self.dataset, self.netlist, self.board, self.params)
        try:
            whole = heuristic.run(
                other,
                self.params,
                self.random,
                observe,
                cancelled,
                dict(self.site.placed),
            )
        except CancelledError:
            raise
        except (RuntimeError, ValueError, KeyError) as error:
            log.warning("the heuristic placer did not finish", error=str(error))
            return
        if not whole:
            log.info("heuristic layout was not whole, keeping the built one")
            return
        Shrink(
            other,
            Spread(other, self.params, self.random),
            self.params,
            observe,
            cancelled,
        ).run()
        theirs = self.measure(other)
        log.info(
            "heuristic contended",
            built=f"{mine[2]}/{mine[3]}",
            heuristic=f"{theirs[2]}/{theirs[3]}",
            kept="heuristic" if theirs < mine else "built",
        )
        if theirs < mine:
            self.site = other

    def measure(self, site: Site) -> tuple[int, int, int, int]:
        """How good a finished layout is: whole first, then small.

        The rectangle is measured the way the report measures it: over the cells inside the
        area, **with the pylons standing**. The grid's own extent counts pipe that ran out
        through the ring, and a layout without its pylons is not the layout that gets built —
        a tighter arrangement whose pylon has to stand further out is not the smaller one.
        """
        x0, y0, x1, y1 = site.area
        size = self.dataset.machines[self.pylon.machine_id].width
        cells = set(site.occupied())
        for spot in site.pylons()[0]:
            cells.update(
                (spot[0] + dx, spot[1] + dy) for dy in range(size) for dx in range(size)
            )
        inside = [c for c in cells if x0 <= c[0] < x1 and y0 <= c[1] < y1]
        if not inside:
            return (len(site.blocks), 0, 0, 0)
        xs = [c[0] for c in inside]
        ys = [c[1] for c in inside]
        return (
            len(site.unplaced()),
            len(site.unrouted()),
            (max(xs) - min(xs) + 1) * (max(ys) - min(ys) + 1),
            site.wire_cells(),
        )

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
            Shrink(self.site, self.spread, self.params, observe, cancelled).run()
            if observe is not None:
                observe(self.spread.frame("build"))
        lucky = self.luckiest(dict(self.site.placed), cancelled)
        self.params = {**self.params, "seed": lucky}
        self.random = random.Random(lucky)
        self.contend(observe, cancelled)
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
