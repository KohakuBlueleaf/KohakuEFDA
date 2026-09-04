"""Hand-maintained basement presets (Core AIC Area squares and depot access) → ``Basement``."""

import json
from importlib import resources

from kohakuefda.model.basement import (
    Basement,
    BusSegment,
    FixedBus,
    LaidBus,
    Region,
)
from kohakuefda.model.names import Names


def _segment(raw: dict) -> BusSegment:
    return BusSegment(x=raw["x"], y=raw["y"], width=raw["width"], depth=raw["depth"])


def _depot(raw: dict) -> FixedBus | LaidBus:
    if raw["kind"] == "fixed":
        return FixedBus(
            port=_segment(raw["port"]) if raw.get("port") else None,
            segments_by_level={
                int(k): [_segment(s) for s in v]
                for k, v in raw["segments_by_level"].items()
            },
            positions_known=raw.get("positions_known", False),
        )
    return LaidBus(
        ports_by_level={int(k): v for k, v in raw["ports_by_level"].items()},
        sections_by_level={int(k): v for k, v in raw["sections_by_level"].items()},
    )


def build_basements() -> dict[str, Basement]:
    text = (
        resources.files("kohakuefda.data.static")
        .joinpath("basements.json")
        .read_text("utf-8")
    )
    raw = json.loads(text)
    out: dict[str, Basement] = {}
    for basement_id, record in raw["basements"].items():
        squares = {
            int(level): (tuple(size) if size else None)
            for level, size in record["square_by_level"].items()
        }
        out[basement_id] = Basement(
            id=basement_id,
            names=Names(**record["names"]),
            region=Region(record["region"]),
            hub=record.get("hub", False),
            square_by_level=squares,
            ring=record.get("ring", 0),
            depot=_depot(record["depot"]),
            source=raw["source"],
        )
    return out
