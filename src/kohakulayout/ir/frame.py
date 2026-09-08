"""The progress envelope: one sampled state of a run, self-contained."""

from kohakulayout.ir.base import Attrs, Model, Rate
from kohakulayout.ir.layout import Layout


class Frame(Model):
    frame_schema: int = 1
    run: str
    seq: int
    at: float
    phase: str
    metrics: dict[str, int | Rate] = {}
    layout: Layout | None = None
    attrs: Attrs = {}
