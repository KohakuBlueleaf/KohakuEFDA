"""The physics protocol: what a pack states, as data shapes and hooks the engine calls.

The signatures here are fixed protocol. Every hook has a default in :mod:`base`, so a pack
overrides only what its game has. The framework never reads a kind or an attr; it asks.
"""

from collections.abc import Iterable
from fractions import Fraction
from typing import Any, Literal, Protocol, runtime_checkable

from kohakulayout.ir import (
    Cell,
    Fabric,
    Finding,
    Footprint,
    Layout,
    Net,
    Placement,
    Refusal,
)
from kohakulayout.ir.base import Model, Rate
from kohakulayout.ir.geometry import XY, Rotation


class Occupant(Model):
    """What holds a cell on a layer: a cell, a wire of a carrier, a unit of a kind, a reservation."""

    kind: Literal["cell", "wire", "unit", "reserve"]
    carrier: str | None = None
    unit_kind: str | None = None
    id: str = ""

    def key(self) -> str:
        return f"{self.kind}:{self.carrier or self.unit_kind or ''}"


class CrossingRule(Model):
    mode: Literal["forbidden", "free", "unit"] = "forbidden"
    unit: Footprint | None = None


class JunctionRule(Model):
    mode: Literal["forbidden", "free", "unit"] = "forbidden"
    split: Footprint | None = None
    merge: Footprint | None = None


class Reach(Model):
    shape: Literal["square", "mask"] = "square"
    radius: int = 0
    cells: tuple[XY, ...] = ()
    partial: bool = True


class Emitter(Model):
    kind: str
    footprint: Footprint
    reach: Reach
    overlap: Literal["allowed", "forbidden"] = "allowed"
    budget: Rate | None = None


class Anchor(Model):
    x: int
    y: int
    rot: Rotation = 0


class UnitPlacement(Model):
    kind: str
    footprint: Footprint
    x: int
    y: int
    rot: Rotation = 0
    owner: str


@runtime_checkable
class Carriers(Protocol):
    def may_share(self, a: Occupant, b: Occupant) -> bool: ...
    def crossing(self, a: str, b: str) -> CrossingRule: ...
    def junction(self, carrier: str) -> JunctionRule: ...
    def run_limit(self, carrier: str) -> int | None: ...
    def repeater(self, carrier: str) -> Footprint | None: ...
    def transfers_through(self, unit_kind: str, carrier: str) -> bool: ...


@runtime_checkable
class Fields(Protocol):
    def needs(self, cell: Cell) -> tuple[str, ...]: ...
    def emitters(self) -> tuple[Emitter, ...]: ...
    def cover(
        self, world: Any, needs: dict[str, tuple[XY, ...]]
    ) -> tuple[UnitPlacement, ...]: ...


@runtime_checkable
class Boundaries(Protocol):
    def anchors(self, world: Any, cell: Cell) -> Iterable[Anchor]: ...
    def legal(self, world: Any, placement: Placement) -> Refusal | None: ...
    def outside(self, world: Any, net: Net) -> tuple[XY, ...]: ...
    def crossing_region(self, carrier: str, region: str) -> bool: ...


@runtime_checkable
class Flow(Protocol):
    evaluates: bool

    def split(self, rate: Fraction, live_outputs: int) -> tuple[Fraction, ...]: ...
    def merge(
        self, rates: tuple[Fraction, ...], capacity: Fraction | None
    ) -> tuple[Fraction, ...]: ...
    def stateful(self) -> bool: ...
    def demand(self, cell: Any, pin: str) -> Fraction | None: ...
    def transfer(
        self, cell: Any, inputs: dict[str, Fraction]
    ) -> dict[str, Fraction] | None: ...


@runtime_checkable
class Rule(Protocol):
    id: str
    severity: str

    def check(
        self, world: Any, layout: Layout, metrics: dict[str, Any]
    ) -> Iterable[Finding]: ...


@runtime_checkable
class Objective(Protocol):
    weights: dict[str, Fraction]

    def terms(
        self, layout: Layout, metrics: dict[str, Any]
    ) -> dict[str, int | Fraction]: ...


@runtime_checkable
class Physics(Protocol):
    id: str
    version: str
    carriers: Carriers
    fields: Fields
    boundaries: Boundaries
    flow: Flow
    rules: tuple[Rule, ...]
    objective: Objective

    def fabric(self, params: dict[str, Any]) -> Fabric: ...
    def library(self) -> dict[str, Footprint]: ...
    def unit_footprints(self) -> dict[str, Footprint]: ...
    def diagnose(self, world: Any, failures: tuple[Refusal, ...]) -> Refusal: ...
