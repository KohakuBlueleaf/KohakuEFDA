"""The evaluation schema: rates per segment and utilisation per machine, as the verify stage fills it."""

from fractions import Fraction

from kohakuefda.model.base import EfdaModel
from kohakuefda.model.rates import Rate

EPSILON = Fraction(1, 1_000_000)


class SegmentFlow(EfdaModel):
    segment_id: str
    items: dict[str, Rate]
    total: Rate
    capacity: Rate


class MachineState(EfdaModel):
    placed_id: str
    machine_id: str
    recipe_id: str | None
    utilisation: Rate
    inputs: dict[str, Rate]
    outputs: dict[str, Rate]
    stalled_by: str = ""


class Evaluation(EfdaModel):
    segments: dict[str, SegmentFlow]
    machines: dict[str, MachineState]
    iterations: int
    converged: bool


__all__ = ["EPSILON", "Evaluation", "MachineState", "SegmentFlow"]
