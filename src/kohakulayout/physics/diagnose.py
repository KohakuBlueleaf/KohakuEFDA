"""The generic diagnostic chain: the first stage that explains a failed attempt."""

from kohakulayout.ir import Refusal
from kohakulayout.ir.refusal import STAGES


def diagnose(failures: tuple[Refusal, ...], order: tuple[str, ...] = STAGES) -> Refusal:
    """The refusal whose stage comes first in ``order``; pack stages sort after the framework's."""
    if not failures:
        return Refusal(stage="legal", subject="", detail="refused for no stated reason")
    rank = {stage: i for i, stage in enumerate(order)}
    return min(
        failures, key=lambda r: (rank.get(r.stage, len(order)), r.subject, r.detail)
    )
