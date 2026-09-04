"""The Rust placement, when it is built.

The whole state goes over once as flat arrays and the search runs on the other side, so nothing
crosses the boundary per move — which is the point: the same walk is about a hundred times
faster there, and a budget that was minutes becomes a moment.

``NATIVE`` is False when the extension is not built and every caller falls back to the Python
search, which stays the reference implementation. ``tests/test_heuristic.py`` holds the two to
identical costs for identical placements, term by term.
"""

import logging

from kohakuefda.layout.heuristic.state import Placement, Weights

try:
    from kohakuefda._native import _Placement

    NATIVE = True
except ImportError:  # the Python search below stands in
    _Placement = None
    NATIVE = False

log = logging.getLogger(__name__)
TURNS = (0, 90, 180, 270)


def build(state: Placement, weights: Weights) -> object | None:
    """Hand the placement over to the native side, or ``None`` when it is not built."""
    if _Placement is None:
        return None
    grid = (state.site.width, state.site.height)
    native = _Placement(
        [[state.size[i][r] for r in range(4)] for i in range(state.count)],
        [[state.offset[i][r] for r in range(4)] for i in range(state.count)],
        [[state.pad[i][r] for r in range(4)] for i in range(state.count)],
        list(state.margin),
        list(state.frozen),
        list(state.wire_from),
        list(state.wire_to),
        [list(group) for group in state.groups],
        list(state.unit_of),
        tuple(state.area_rect),
        grid,
    )
    native.weigh(
        weights.area,
        weights.wire,
        weights.overlap,
        weights.group,
        weights.shut,
        weights.crowd,
        weights.tight,
        weights.jam,
        weights.slack,
    )
    return native


def send(native: object, state: Placement) -> None:
    """Put the Python placement's anchors, heat and clearances on the native side."""
    native.adopt(
        [(state.x[i], state.y[i], state.rotation[i] // 90) for i in range(state.count)]
    )


def receive(native: object, state: Placement) -> None:
    """Take the native side's anchors back into the Python placement."""
    state.adopt(
        {
            state.ids[i]: (x, y, TURNS[rotation])
            for i, (x, y, rotation) in enumerate(native.anchors())
        }
    )


def anneal(native: object, state: Placement, params: dict, seed: int) -> tuple:
    """Run the native walk over the placement and bring the answer back."""
    send(native, state)
    trace = native.anneal(
        seed & 0xFFFFFFFF,
        max(1, int(params["sa_moves"])),
        max(1, int(params["sa_window"])),
        max(1, int(params["sa_warmup"])),
        float(params["sa_accept_initial"]),
        max(1e-9, float(params["sa_end_temperature"])),
        float(params["sa_range_start"]),
        max(1, int(params["sa_range_floor"])),
        (
            float(params["move_displace"]),
            float(params["move_swap"]),
            float(params["move_rotate"]),
            float(params["move_shift"]),
        ),
        max(0, int(params["sa_polish"])),
        float(params["sa_polish_overlap"]),
    )
    receive(native, state)
    return trace
