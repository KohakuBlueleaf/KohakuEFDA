"""One wrapper per accelerated function. ``None`` means: use the Python path.

Levels cross the boundary as canonical JSON strings. The kernel does not live here: it
crosses by handle and is selected in ``kohakulayout.state.kernel``. ``KOHAKULAYOUT_BACKEND``
set to ``python`` disables every wrapper; ``native`` makes a missing module an error.
"""

import os
from typing import Any

from kohakulayout._rust import HAS_RUST, kohakulayout_rs
from kohakulayout.errors import NotAvailable

BACKEND = os.environ.get("KOHAKULAYOUT_BACKEND", "auto")


def native_wanted() -> bool:
    if BACKEND == "python":
        return False
    if BACKEND == "native" and not HAS_RUST:
        raise NotAvailable(
            "KOHAKULAYOUT_BACKEND=native but kohakulayout_rs is not built; run maturin develop"
        )
    return HAS_RUST


def rust_parse_kl(text: str, context: str | None = None) -> str | None:
    """JSON of the levels in ``text`` (version, physics, params, fabric, netlist, layout, assessment), or None."""
    if not native_wanted() or not hasattr(kohakulayout_rs, "parse_kl"):
        return None
    try:
        return kohakulayout_rs.parse_kl(text, context)
    except Exception:  # noqa: BLE001
        return None


def rust_write_kl(level_json: str, context: str | None = None) -> str | None:
    """Canonical text of a level given as content JSON, or None; a layout takes its problem as ``context``."""
    if not native_wanted() or not hasattr(kohakulayout_rs, "write_kl"):
        return None
    try:
        return kohakulayout_rs.write_kl(level_json, context)
    except Exception:  # noqa: BLE001
        return None


def rust_flatten(level_json: str) -> str | None:
    if not native_wanted() or not hasattr(kohakulayout_rs, "flatten"):
        return None
    try:
        return kohakulayout_rs.flatten(level_json)
    except Exception:  # noqa: BLE001
        return None


def rust_digest(level_json: str) -> str | None:
    if not native_wanted() or not hasattr(kohakulayout_rs, "digest"):
        return None
    try:
        return kohakulayout_rs.digest(level_json)
    except Exception:  # noqa: BLE001
        return None


def rust_astar(
    grid: Any,
    layer: str,
    sources: list,
    targets: list,
    rules: Any,
    avoid: list | None = None,
    own: list | None = None,
) -> str | None:
    """The native path search on a native grid: the found path as JSON, ``none``, or None to use Python."""
    if not native_wanted() or not hasattr(grid, "astar"):
        return None
    try:
        answer = grid.astar(layer, sources, targets, rules(), avoid or [], own or [])
    except Exception:  # noqa: BLE001
        return None
    return "none" if answer is None else answer
