"""The evaluator slot: rates per pin and per net for a netlist under a pack's flow hooks, with findings."""

from typing import Any

from kohakulayout.errors import KohakuLayoutError
from kohakulayout.flow.fixedpoint import Evaluation, FixedPoint
from kohakulayout.ir import Netlist

EVALUATORS: dict[str, type] = {FixedPoint.id: FixedPoint}


def evaluate(
    netlist: Netlist,
    flow: Any,
    fabric: Any = None,
    evaluator: str = "fixedpoint",
    **options: Any,
) -> Evaluation:
    """Run the named evaluator; an unknown one is named, not crashed on."""
    cls = EVALUATORS.get(evaluator)
    if cls is None:
        raise KohakuLayoutError(
            f"no flow evaluator {evaluator!r}; known: {sorted(EVALUATORS)}"
        )
    return cls(**options).evaluate(netlist, flow, fabric)


__all__ = ["EVALUATORS", "Evaluation", "evaluate"]
