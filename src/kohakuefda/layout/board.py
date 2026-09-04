"""The basement's geometry for one scenario: square, ring, fixed bus cells and brick slots."""

from kohakuefda.layout.depot_via import Slot, fixed_slots
from kohakuefda.model.basement import DEFAULT_SQUARE
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.layout import Cell, Rect
from kohakuefda.model.plan import Finding
from kohakuefda.model.scenario import Scenario


class Board:
    """Square size, ring depth, fixed bus cells and slots, all in grid coordinates."""

    def __init__(
        self,
        square: tuple[int, int],
        ring: int,
        slots: list[Slot],
        fixed: set[Cell],
        findings: list[Finding],
    ) -> None:
        self.square = square
        self.ring = ring
        self.slots = slots
        self.fixed = fixed
        self.findings = findings

    @property
    def grid(self) -> tuple[int, int]:
        return (self.square[0] + 2 * self.ring, self.square[1] + 2 * self.ring)

    @property
    def area(self) -> Rect:
        return (
            self.ring,
            self.ring,
            self.ring + self.square[0],
            self.ring + self.square[1],
        )


def board_of(dataset: Dataset, scenario: Scenario) -> Board:
    """Square, ring depth, fixed bus cells and brick slots for the scenario's basement."""
    basement = dataset.basements.get(scenario.basement.basement_id)
    square = basement.square(scenario.basement.level) if basement else None
    findings: list[Finding] = []
    if square is None:
        square = DEFAULT_SQUARE
        findings.append(
            Finding(
                rule="layout.square_unknown",
                severity="warning",
                subject=scenario.basement.basement_id,
                message=f"square size unknown for this basement and level; using {DEFAULT_SQUARE[0]}×{DEFAULT_SQUARE[1]}",
            )
        )
    ring = basement.ring if basement else 0
    slots = [
        Slot(s.x + ring, s.y + ring, s.side)
        for s in fixed_slots(dataset, scenario.basement)
    ]
    fixed: set[Cell] = set()
    if basement is not None and basement.depot.kind == "fixed":
        segments = list(basement.depot.segments(scenario.basement.depot_level))
        if basement.depot.port is not None:
            segments.append(basement.depot.port)
        for segment in segments:
            x0, y0, x1, y1 = segment.rect
            fixed |= {
                (x + ring, y + ring) for y in range(y0, y1) for x in range(x0, x1)
            }
    return Board(square, ring, slots, fixed, findings)
