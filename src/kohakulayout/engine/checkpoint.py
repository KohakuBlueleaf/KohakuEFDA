"""Checkpoints: enough to rebuild the engine and continue a run, as one JSON artifact."""

import json
from pathlib import Path
from typing import Any

from kohakulayout.ir import Layout, Model
from kohakulayout.ir.base import jsonable


class Checkpoint(Model):
    run: str
    seq: int
    solver: str = ""
    params: dict[str, Any] = {}
    seed: int = 0
    rng_state: Any = None
    budget: dict[str, Any] = {}
    phase: str = ""
    layout: Layout
    best: Layout | None = None
    best_metrics: dict[str, Any] = {}
    attempts: int = 0
    accepts: int = 0
    attrs: dict[str, Any] = {}

    def to_json(self) -> str:
        return json.dumps(jsonable(self.model_dump()), sort_keys=True, indent=2)

    @classmethod
    def from_json(cls, text: str) -> "Checkpoint":
        return cls.model_validate(json.loads(text))


def rng_state_jsonable(state: Any) -> Any:
    return jsonable(list(state) if isinstance(state, tuple) else state)


def rng_state_native(state: Any) -> Any:
    """The tuple shape ``random.Random.setstate`` wants, back from its JSON form."""
    if isinstance(state, list):
        return tuple(rng_state_native(s) for s in state)
    return state


def save(checkpoint: Checkpoint, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(checkpoint.to_json())
    return path


def load(path: Path) -> Checkpoint:
    return Checkpoint.from_json(path.read_text())


__all__ = ["Checkpoint", "load", "rng_state_jsonable", "rng_state_native", "save"]
