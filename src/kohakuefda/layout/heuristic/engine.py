"""Running a heuristic search and turning what it found into a real layout.

The search works on anchors alone, which is what makes it fast; the answer still has to be
built. ``materialise`` puts every block down through ``Site.place``, which routes what it
touches and refuses anything the game would, so what comes back is a layout or nothing.

Placing in a different order gives different lane paths, so a placement that will not build in
the flow's order is offered a few other orders before it is given up on.
"""

import logging
import random

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


def search(state: Placement, params: dict, rng, observe, cancelled) -> None:
    """Run whichever search is asked for over the placement."""
    if str(params["heuristic"]) == "evolve":
        Evolver(state, params, rng).run(state.anchors(), observe, cancelled)
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
    log.info("heuristic start", search=how, blocks=state.count, area=state.terms.area)
    budget = int(params["sa_moves"])
    for attempt in range(rounds):
        settings = {**params, "sa_moves": budget if not attempt else budget // 2}
        search(state, settings, rng, observe, cancelled)
        if materialise(site, spread, state.anchors(), int(params["build_tries"])):
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
        state.terms = state.recompute()
        log.info(
            "build failed, widening",
            round=attempt + 1,
            homeless=len(site.unplaced()),
            widened=len(blocked),
        )
    return False


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
