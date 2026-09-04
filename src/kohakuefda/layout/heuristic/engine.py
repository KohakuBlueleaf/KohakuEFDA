"""Running a heuristic search and turning what it found into a real layout.

The search works on anchors alone, which is what makes it fast; the answer still has to be
built. ``materialise`` puts every block down through ``Site.place``, which routes what it
touches and refuses anything the game would, so what comes back is a layout or nothing.

Placing in a different order gives different lane paths, so a placement that will not build in
the flow's order is offered a few other orders before it is given up on.
"""

import logging
import random

from kohakuefda.layout.heuristic import native
from kohakuefda.layout.heuristic.anneal import Annealer
from kohakuefda.layout.heuristic.genetic import Evolver
from kohakuefda.layout.heuristic.seed import start
from kohakuefda.layout.heuristic.state import Placement, Weights
from kohakuefda.layout.site import Site
from kohakuefda.layout.spread import Spread

log = logging.getLogger(__name__)
SEARCHES = ("anneal", "evolve")


def materialise(site: Site, spread: Spread, anchors: dict, tries: int) -> bool:
    """Build the placement for real: every block down, then every lane routed at once.

    Placing and routing a machine at a time makes each lane take the best path it can see,
    which strands the lanes that come after it. The geometry goes down first — the search has
    already made it overlap-free — and the whole netlist is then routed together with rip-up
    and negotiated congestion, which is what that router is for.
    """
    for block_id in list(site.placed):
        site.remove(block_id)
    for block_id in spread.order():
        anchor = anchors.get(block_id)
        if anchor is None:
            return False
        if not site.place(block_id, *anchor, route=False):
            return False
    site.router.route(strict=False)
    return not site.unplaced() and not site.unrouted()


def search(state: Placement, params: dict, rng, observe, cancelled, fast=None) -> None:
    """Run whichever search is asked for over the placement.

    The native walk takes the whole state over once and runs about a hundred times faster, so
    it is used whenever the extension is built and a watcher does not need to see the walk;
    the Python search is the reference and stands in otherwise.
    """
    if str(params["heuristic"]) == "evolve":
        Evolver(state, params, rng).run(state.anchors(), observe, cancelled)
    elif fast is not None and observe is None:
        native.anneal(fast, state, params, rng.randrange(1 << 32))
    else:
        Annealer(state, params, rng).run(observe, cancelled)


def run(
    site: Site,
    params: dict,
    rng: random.Random,
    observe=None,
    cancelled=None,
) -> bool:
    """Search for a placement and build it; ``True`` when a whole layout came out.

    A placement that scores well can still be unbuildable: the search prices the room a lane
    needs to leave a port, not the path it then has to find. So a build that fails says which
    machines it failed on, those machines ask for another cell of room, and the search runs
    again knowing it — the placement-level form of negotiated congestion.
    """
    how = str(params["heuristic"])
    rounds = max(1, int(params["route_rounds"]))
    widest = max(0, int(params["route_widest"]))
    state = Placement(site, Weights.of(params))
    spread = Spread(site, params, rng)
    anchors = start(site, state, params, rng)
    state.adopt(anchors)
    fast = (
        native.build(state, Weights.of(params))
        if str(params["native"]) != "off"
        else None
    )
    log.info(
        "heuristic start",
        search=how,
        blocks=state.count,
        area=state.terms.area,
        native=fast is not None,
    )
    budget = int(params["sa_moves"])
    for attempt in range(rounds):
        settings = {**params, "sa_moves": budget if not attempt else budget // 2}
        search(state, settings, rng, observe, cancelled, fast)
        anchors = state.anchors()
        if materialise(site, spread, anchors, int(params["build_tries"])) or repair(
            site, spread, state, anchors, int(params["repair_tries"])
        ):
            log.info(
                "heuristic done",
                round=attempt + 1,
                area=state.terms.area,
                wires=site.wire_cells(),
            )
            return not site.unrouted()
        blocked = crowded(site, state)
        for block in blocked:
            state.extra[block] = min(widest, state.extra[block] + 1)
        state.cool(float(params["route_cool"]))
        scorch(site, state, float(params["route_heat"]))
        state.terms = state.recompute()
        if fast is not None:
            fast = native.build(state, Weights.of(params))
        log.info(
            "build failed, widening",
            round=attempt + 1,
            homeless=len(site.unplaced()),
            widened=len(blocked),
        )
    return False


def repair(
    site: Site, spread: Spread, state: Placement, anchors: dict, tries: int
) -> bool:
    """Nudge the machines whose lanes had no path, with the router itself as the judge.

    The search prices the room a lane needs, not the path it finds, so a placement can be
    good by every term it knows and still leave one lane stranded. Here the true router says
    whether a change helped, which is affordable because only a handful of machines and a
    handful of positions are worth trying. Whatever happens the site is left holding the best
    arrangement tried, not the last one.
    """
    best = len(site.unrouted()) + len(site.unplaced())
    kept = dict(anchors)
    for _ in range(max(1, tries)):
        if not best:
            break
        moved = False
        for block in ends(site, state):
            block_id = state.ids[block]
            home = anchors[block_id]
            for spot in offers(state, block, home):
                anchors[block_id] = spot
                build(site, spread, anchors)
                count = len(site.unrouted()) + len(site.unplaced())
                if count < best:
                    best, moved, kept = count, True, dict(anchors)
                    break
                anchors[block_id] = home
            if not best:
                break
        if not moved:
            break
    anchors.clear()
    anchors.update(kept)
    build(site, spread, kept)
    return not site.unrouted() and not site.unplaced()


def ends(site: Site, state: Placement) -> list[int]:
    """The movable machines at either end of a lane that has no path."""
    out = []
    for wire in site.unrouted():
        for key in (wire.source, wire.sink):
            index = state.index[site.owner[key].id]
            if not state.frozen[index] and index not in out:
                out.append(index)
    return out


def offers(state: Placement, block: int, home: tuple) -> list[tuple[int, int, int]]:
    """Where one machine might go instead: turned where it stands, or a cell or two over."""
    out = []
    for rotation in (0, 90, 180, 270):
        for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1), (2, 0), (0, 2)):
            spot = (home[0] + dx, home[1] + dy, rotation)
            if spot != home:
                out.append(spot)
    return out


def build(site: Site, spread: Spread, anchors: dict) -> None:
    """Put every block down and route the whole netlist, whatever comes of it.

    The router reads a pin table that only holds placed machines, so a layout missing one is
    not offered to it at all: the caller sees the machines that would not stand instead.
    """
    for block_id in list(site.placed):
        site.remove(block_id)
    for block_id in spread.order():
        anchor = anchors.get(block_id)
        if anchor is not None:
            site.place(block_id, *anchor, route=False)
    if not site.unplaced():
        site.router.route(strict=False)


def scorch(site: Site, state: Placement, amount: float) -> None:
    """Leave heat over the ground every lane without a path wanted.

    The rectangle between a lane's two pins is where it had to run; whatever is standing in
    it is what stopped it. Heat there is a cost the search can see and move off, which block
    inflation is not: inflating a machine says "be bigger", heat says "not here".
    """
    for wire in site.unrouted():
        source = site.owner[wire.source]
        sink = site.owner[wire.sink]
        a = source.pin_outside(wire.source)
        b = sink.pin_outside(wire.sink)
        x0, x1 = sorted((a[0], b[0]))
        y0, y1 = sorted((a[1], b[1]))
        state.warm(
            ((x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)),
            amount,
        )


def crowded(site: Site, state: Placement) -> list[int]:
    """The blocks a failed build could not fit, and the ends of every lane with no path.

    Once the placement is dense enough that everything stands, what is left is lanes with
    nowhere to run. The machines at each end of such a lane are the ones asking for room, so
    they are the ones widened — the congestion the router met, handed back to the search.
    """
    out = set()
    for block_id in site.unplaced():
        out.add(state.index[block_id])
        for wire in site.touching[block_id]:
            for key in (wire.source, wire.sink):
                out.add(state.index[site.owner[key].id])
    for wire in site.unrouted():
        for key in (wire.source, wire.sink):
            out.add(state.index[site.owner[key].id])
    return sorted(index for index in out if not state.frozen[index])
