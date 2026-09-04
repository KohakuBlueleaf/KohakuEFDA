"""Where a search starts.

Blocks pinned to a bus slot or a border cell have only a handful of legal positions, and the
search never moves them, so they are settled first and directly from the positions the game
allows — not by running the constructive spread and hoping it placed them, which it need not
do and which would leave a machine at the origin, outside the area, for the search to inherit.

``scatter`` is the honest start for a heuristic: nothing about the free blocks' arrangement is
inherited from the greedy pass. ``construct`` starts from what the spread built, filling in
anything it could not place. ``best-of`` draws several scatters and keeps the cheapest.
"""

import logging
import random

from kohakuefda.layout.heuristic.state import Placement
from kohakuefda.layout.site import Site
from kohakuefda.layout.spread import Spread

log = logging.getLogger(__name__)
STARTS = ("construct", "scatter", "best-of")
PINNED = ("slot", "edge")
Anchors = dict[str, tuple[int, int, int]]


def _spread(site: Site, params: dict, rng: random.Random, attempts: int) -> Spread:
    return Spread(
        site, {**params, "spread_attempts": attempts, "search": "restart"}, rng
    )


def held(site: Site, block_id: str) -> bool:
    """Whether the search must leave this block where the seed put it.

    A brick has to sit with its back face flush on a bus part and a machine inside its gas
    unit's zone (DEP-06, ENV-02) — rules about *how* two blocks meet, which a cost term over
    distances cannot express. Those clusters are arranged by the constructive pass and the
    search arranges everything else around them.
    """
    block = site.blocks[block_id]
    return block.constraint in PINNED or bool(block.group)


def pinned(site: Site, params: dict, rng: random.Random) -> Anchors:
    """A legal position for every block the search may not move."""
    spread = _spread(site, params, rng, max(1, int(params["seed_attempts"])))
    spread.run()
    out: Anchors = {b: a for b, a in site.placed.items() if held(site, b)}
    missing = [b for b in site.blocks if held(site, b) and b not in out]
    if missing:
        for block_id in missing:
            for anchor in spread.anchors_for(block_id) or ():
                if site.place(block_id, *anchor, route=False):
                    out[block_id] = anchor
                    break
            else:
                log.warning("nowhere to pin a block", block=block_id)
    return out


def scatter(state: Placement, base: Anchors, rng: random.Random) -> Anchors:
    """The pinned blocks where they belong, everything else thrown at the board."""
    out = dict(base)
    for index, block_id in enumerate(state.ids):
        if block_id in out:
            continue
        x0, y0, x1, y1 = state.room(index)
        rotation = rng.choice((0, 90, 180, 270))
        width, height = state.size[index][rotation // 90]
        out[block_id] = (
            rng.randint(x0, max(x0, x1 - width)),
            rng.randint(y0, max(y0, y1 - height)),
            rotation,
        )
    return out


def start(site: Site, state: Placement, params: dict, rng: random.Random) -> Anchors:
    """The placement a search begins from, by the ``start`` setting.

    Whatever the setting, every block comes back with a position: a search that inherits a
    block still sitting at the origin will never move it and can never be built.
    """
    how = str(params["start"])
    base = pinned(site, params, rng)
    if how == "construct":
        return scatter(state, {**base, **dict(site.placed)}, rng)
    draws = max(1, int(params["seed_draws"])) if how == "best-of" else 1
    best: tuple[float, Anchors] | None = None
    for _ in range(draws):
        anchors = scatter(state, base, rng)
        state.adopt(anchors)
        cost = state.cost()
        if best is None or cost < best[0]:
            best = (cost, anchors)
    return best[1]
