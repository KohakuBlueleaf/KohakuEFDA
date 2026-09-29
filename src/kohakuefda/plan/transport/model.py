"""The exact contract of a direct-port transport allocation."""

import hashlib
from dataclasses import dataclass, field
from fractions import Fraction

from kohakuefda.model.cells import Netlist


class TransportError(ValueError):
    """A transport operating point cannot be represented exactly and physically."""


@dataclass(frozen=True)
class Transfer:
    net: str
    source: str
    sink: str
    rate: Fraction


@dataclass
class TransportResult:
    source_digest: str = ""
    duties: dict[str, Fraction] = field(default_factory=dict)
    transfers: list[Transfer] = field(default_factory=list)
    feasible: bool = False
    optimal: bool = False
    reason: str = ""
    seconds: float = 0.0
    lanes: int = 0


def fingerprint(netlist: Netlist) -> str:
    """Identify the complete source netlist of an allocation."""
    return hashlib.sha256(netlist.model_dump_json().encode("utf-8")).hexdigest()


__all__ = ["Transfer", "TransportError", "TransportResult", "fingerprint"]
