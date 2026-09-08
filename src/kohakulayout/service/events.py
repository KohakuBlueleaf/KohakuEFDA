"""The event log: one JSON line per event, and a reader that rebuilds typed payloads and applies a filter."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from kohakulayout.engine.checkpoint import Checkpoint
from kohakulayout.engine.progress import Event
from kohakulayout.ir import Assessment, Frame, Refusal
from kohakulayout.ir.base import jsonable
from kohakulayout.service.protocol import EventFilter

PAYLOADS: dict[str, Any] = {
    "frame": Frame,
    "assessment": Assessment,
    "refusal": Refusal,
    "checkpoint": Checkpoint,
}


def encode(event: Event) -> str:
    payload = event.payload
    if hasattr(payload, "content"):
        payload = payload.content()
    elif hasattr(payload, "model_dump"):
        payload = payload.model_dump()
    return json.dumps(
        {
            "kind": event.kind,
            "run": event.run,
            "seq": event.seq,
            "at": event.at,
            "payload": jsonable(payload),
        },
        sort_keys=True,
    )


def decode(line: str) -> Event:
    raw = json.loads(line)
    cls = PAYLOADS.get(raw["kind"])
    if isinstance(raw["payload"], dict):
        raw["payload"].pop("level", None)
    payload = (
        cls.model_validate(raw["payload"])
        if cls is not None and isinstance(raw["payload"], dict)
        else raw["payload"]
    )
    return Event(
        kind=raw["kind"], run=raw["run"], seq=raw["seq"], at=raw["at"], payload=payload
    )


class JsonlSink:
    """Appends every event to a file as it happens, flushed per line so a reader sees it live."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._file = path.open("a", encoding="utf-8")
        self.count = 0

    def emit(self, event: Event) -> None:
        self._file.write(encode(event) + "\n")
        self._file.flush()
        self.count += 1

    def close(self) -> None:
        self._file.close()


def read_events(path: Path, filter: EventFilter | None = None) -> Iterator[Event]:
    if not path.exists():
        return
    filter = filter if filter is not None else EventFilter()
    frames = 0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            event = decode(line)
            index = frames
            if event.kind == "frame":
                frames += 1
            if filter.admits(event, index):
                yield event


__all__ = ["PAYLOADS", "JsonlSink", "decode", "encode", "read_events"]
