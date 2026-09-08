"""Snapshots: a token holding everything a world needs to come back byte for byte."""

from dataclasses import dataclass, field
from typing import Any

from kohakulayout.ir import Placement, Reservation, Unit, Wire


@dataclass(frozen=True)
class Token:
    seq: int
    placements: dict[str, Placement]
    wires: dict[str, Wire]
    units: dict[str, Unit]
    reservations: tuple[Reservation, ...]
    membership: dict[str, str]
    kernel: bytes
    digest: str
    extra: dict[str, Any] = field(default_factory=dict)
