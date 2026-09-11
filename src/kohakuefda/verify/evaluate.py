"""A project layout evaluated by the framework: the reverse translation under the routed evaluator, read back as the project's evaluation."""

from fractions import Fraction

from kohakuefda.flow.evaluate import Evaluation, MachineState, SegmentFlow
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.layout import Layout
from kohakuefda.physics.flow import LINK
from kohakuefda.synth.reverse import Reverse, kl_name, link_id
from kohakulayout.flow import evaluate as evaluate_flow

Mix = dict[str, Fraction]


def _merge(mixes: list[Mix]) -> Mix:
    out: Mix = {}
    for mix in mixes:
        for key, rate in mix.items():
            if rate > 0:
                out[key] = out.get(key, Fraction(0)) + rate
    return out


def evaluate(dataset: Dataset, layout: Layout) -> Evaluation:
    """Rates per segment and utilisation per machine, from the routed evaluator over the layout's reverse translation."""
    reverse = Reverse(dataset, layout)
    problem, kl_layout = reverse.problem()
    result = evaluate_flow(
        problem.netlist,
        reverse.physics.flow,
        problem.fabric,
        evaluator=reverse.physics.flow.evaluator,
        layout=kl_layout,
        oriented=True,
    )
    unit_cells = {
        net_id: {(kl_layout.units[u].x, kl_layout.units[u].y) for u in wire.units}
        for net_id, wire in kl_layout.wires.items()
    }
    by_cells = {frozenset(s.cells): s for s in layout.segments}
    links = {
        (source.owner, target.owner): (link_id(source, reverse.names), source.carrier)
        for source, target in reverse.conn.links
    }
    capacities = {
        "belt": dataset.constants.belt_per_min,
        "pipe": dataset.constants.pipe_per_min,
    }
    segments: dict[str, SegmentFlow] = {}
    for run in result.runs.values():
        bare = frozenset(c for c in run.cells if c not in unit_cells.get(run.net, ()))
        segment = by_cells.get(bare) if bare else None
        if segment is not None:
            segments[segment.id] = SegmentFlow(
                segment_id=segment.id,
                items=dict(run.mix),
                total=run.total,
                capacity=capacities[segment.kind],
            )
            continue
        owners = (_owner(run.source), _owner(run.target))
        found = links.get(owners) or links.get(owners[::-1])
        if found is not None:
            segments[found[0]] = SegmentFlow(
                segment_id=found[0],
                items=dict(run.mix),
                total=run.total,
                capacity=capacities[found[1]],
            )
    machines: dict[str, MachineState] = {}
    for placed in layout.machines:
        state = result.cells.get(kl_name(placed.id))
        if state is None or not dataset.machines[placed.machine_id].ports:
            continue
        machines[placed.id] = MachineState(
            placed_id=placed.id,
            machine_id=placed.machine_id,
            recipe_id=placed.recipe_id,
            utilisation=state.load if state.load is not None else Fraction(0),
            inputs=_merge([m for p, m in state.received.items() if p != LINK]),
            outputs=dict(state.made),
            stalled_by=state.note,
        )
    return Evaluation(
        segments=segments,
        machines=machines,
        iterations=result.rounds,
        converged=result.converged,
    )


def _owner(node_id: str) -> str:
    """The cell or unit a graph node belongs to: ``cell.pin``, ``net/unit`` or ``net/unit:axis``."""
    if "/" in node_id:
        return node_id.rsplit("/", 1)[1].split(":")[0]
    return node_id.rsplit(".", 1)[0]


__all__ = ["evaluate"]
