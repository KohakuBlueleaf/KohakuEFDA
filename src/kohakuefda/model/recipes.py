"""Recipes (the game's machine crafts) with port bindings."""

from fractions import Fraction

from kohakuefda.model.base import EfdaModel
from kohakuefda.model.items import Phase
from kohakuefda.model.names import Names
from kohakuefda.model.rates import Rate, per_minute


class Stack(EfdaModel):
    """``count`` units of ``item_id`` per craft."""

    item_id: str
    count: int


class Binding(EfdaModel):
    """A buffer index bound to the machine port indices it may use."""

    buffer: int
    ports: list[int]
    phase: Phase | None = None


class Recipe(EfdaModel):
    """One craft: machine, mode, inputs, outputs, duration and which port each product uses.

    ``event`` marks a limited-time recipe (game-knowledge RCP-06).
    """

    id: str
    names: Names
    machine_id: str
    mode: str
    group_id: str
    inputs: list[Stack]
    outputs: list[Stack]
    seconds: Rate
    env: str | None = None
    event: bool = False
    buffers: dict[str, int] = {}
    belt_in: list[Binding] = []
    belt_out: list[Binding] = []
    pipe_in: list[Binding] = []
    pipe_out: list[Binding] = []

    def input_rate(self, item_id: str) -> Fraction:
        return sum(
            (
                per_minute(s.count, self.seconds)
                for s in self.inputs
                if s.item_id == item_id
            ),
            Fraction(0),
        )

    def output_rate(self, item_id: str) -> Fraction:
        return sum(
            (
                per_minute(s.count, self.seconds)
                for s in self.outputs
                if s.item_id == item_id
            ),
            Fraction(0),
        )

    @property
    def crafts_per_minute(self) -> Fraction:
        return per_minute(1, self.seconds)

    def output_ports(self, item_id: str, fluid: bool) -> list[int]:
        """Port indices that emit ``item_id``: pipe bindings for fluids, belt bindings otherwise."""
        buffer = self.buffers.get(item_id)
        if buffer is None:
            return []
        bindings = self.pipe_out if fluid else self.belt_out
        return [port for b in bindings if b.buffer == buffer for port in b.ports]

    def input_ports(self, item_id: str, fluid: bool) -> list[int]:
        """Port indices that accept ``item_id``: pipe bindings for fluids, belt bindings otherwise."""
        buffer = self.buffers.get(item_id)
        if buffer is None:
            return []
        bindings = self.pipe_in if fluid else self.belt_in
        return [port for b in bindings if b.buffer == buffer for port in b.ports]
