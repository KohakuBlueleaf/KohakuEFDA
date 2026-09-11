"""The evaluator slot: rates per pin and per net for a netlist, or per run over a layout, under a pack's flow hooks, with findings."""

from typing import Any

from kohakulayout.errors import KohakuLayoutError
from kohakulayout.flow.fixedpoint import Evaluation, FixedPoint
from kohakulayout.flow.routed import Routed
from kohakulayout.ir import Netlist

EVALUATORS: dict[str, type] = {FixedPoint.id: FixedPoint, Routed.id: Routed}


def evaluate(
    netlist: Netlist,
    flow: Any,
    fabric: Any = None,
    evaluator: str = "fixedpoint",
    layout: Any = None,
    **options: Any,
) -> Evaluation:
    """Run the named evaluator; an unknown one is named, not crashed on; ``layout`` goes to the evaluators that read one."""
    cls = EVALUATORS.get(evaluator)
    if cls is None:
        raise KohakuLayoutError(
            f"no flow evaluator {evaluator!r}; known: {sorted(EVALUATORS)}"
        )
    return cls(**options).evaluate(netlist, flow, fabric, layout=layout)


__all__ = ["EVALUATORS", "Evaluation", "evaluate"]
