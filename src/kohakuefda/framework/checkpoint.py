"""Portable snapshot checkpoints; importing one always rechecks its realization."""

import json
from dataclasses import asdict
from pathlib import Path

from pydantic import TypeAdapter

from kohakuefda.framework.control import ConfigurationError
from kohakuefda.model.solver import Snapshot

SCHEMA = 1
SNAPSHOT = TypeAdapter(Snapshot)


def save_snapshot(snapshot: Snapshot, path: Path) -> None:
    """Write a JSON snapshot, not solver-private search history."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps({"schema": SCHEMA, "snapshot": asdict(snapshot)}, indent=1),
        encoding="utf-8",
    )
    temporary.replace(path)


def load_snapshot(path: Path) -> Snapshot:
    """Decode a checkpoint; Context.import_snapshot validates it against the problem."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != SCHEMA:
        raise ConfigurationError("unsupported snapshot checkpoint schema")
    return SNAPSHOT.validate_python(data["snapshot"])
