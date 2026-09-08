"""Progress: one event envelope for everything observable, and the sinks that receive it."""

from collections.abc import Callable
from typing import Any, Literal, Protocol, runtime_checkable

from kohakulayout.ir import Model
from kohakulayout.ir.base import digest_of, jsonable

EventKind = Literal["status", "frame", "assessment", "refusal", "checkpoint", "log"]


class Event(Model):
    kind: EventKind
    run: str
    seq: int
    at: float
    payload: Any = None

    def content(self) -> dict[str, Any]:
        payload = self.payload
        if hasattr(payload, "content"):
            payload = payload.content()
        elif hasattr(payload, "model_dump"):
            payload = payload.model_dump()
        payload = jsonable(payload)
        if isinstance(payload, dict):
            payload = {k: v for k, v in payload.items() if k != "at"}
        return {"kind": self.kind, "run": self.run, "seq": self.seq, "payload": payload}


@runtime_checkable
class Sink(Protocol):
    def emit(self, event: Event) -> None: ...


class NullSink:
    def emit(self, event: Event) -> None:
        return None


class ListSink:
    """Keeps every event; ``digest`` hashes them without their timestamps, for reproducibility checks."""

    def __init__(self) -> None:
        self.events: list[Event] = []

    def emit(self, event: Event) -> None:
        self.events.append(event)

    def of(self, kind: str) -> list[Event]:
        return [e for e in self.events if e.kind == kind]

    def digest(self) -> str:
        return digest_of([e.content() for e in self.events])


class CallbackSink:
    def __init__(self, fn: Callable[[Event], None]) -> None:
        self.fn = fn

    def emit(self, event: Event) -> None:
        self.fn(event)


__all__ = ["CallbackSink", "Event", "EventKind", "ListSink", "NullSink", "Sink"]
