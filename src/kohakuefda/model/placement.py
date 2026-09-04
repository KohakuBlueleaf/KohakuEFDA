"""The placement checkpoint: where every block sits, which port each pin uses, the pylons,
the outside inputs and the cost terms of the layout the engine chose."""

import json
from pathlib import Path

from kohakuefda.model.base import EfdaModel
from kohakuefda.model.geometry import Rotation
from kohakuefda.model.layout import Cell, Entry, Rect
from kohakuefda.model.plan import Finding


class PlacedBlock(EfdaModel):
    """One block at an anchor with a rotation; size unrotated; ``ports`` maps a pin id to the
    index of the alternative port it uses (``0`` is the pin's default)."""

    id: str
    x: int
    y: int
    rotation: Rotation = 0
    width: int
    height: int
    ports: dict[str, int] = {}


class Placement(EfdaModel):
    """Block anchors in grid cells, the area inside the grid, pylons, entries, the cost."""

    schema_version: int = 3
    dataset_version: str
    square: tuple[int, int]
    grid: tuple[int, int]
    area: Rect
    gap: int
    cost: float
    terms: dict[str, float] = {}
    blocks: list[PlacedBlock] = []
    pylons: list[Cell] = []
    entries: list[Entry] = []
    findings: list[Finding] = []

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=1) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "Placement":
        return cls.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def block(self, block_id: str) -> PlacedBlock:
        return next(b for b in self.blocks if b.id == block_id)
