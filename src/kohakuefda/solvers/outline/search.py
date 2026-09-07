"""Complete routed fixed-outline trajectories over target-directed physical moves."""

from kohakuefda.solvers.local.policy import Decision, decide
from kohakuefda.solvers.local.search import Trajectory
from kohakuefda.solvers.outline.moves import OutlineMoves


class OutlineTrajectory(Trajectory):
    """Keep every machine routed while reducing overflow of the immutable target."""

    def __init__(self, workspace, settings, method):
        super().__init__(workspace.context, settings, method)
        self.workspace = workspace
        x0, y0, x1, y1 = workspace.backend.target.area
        self.normalizer = (x1 - x0) * (y1 - y0)

    def layout_moves(self):
        return OutlineMoves(
            self.context, self.settings, self.workspace.backend.target.area
        )

    def steps(self, phase):
        for step in super().steps(phase):
            if self.workspace.parent.current is not None:
                break
            yield step

    def choose(self, parent, candidate, phase, heat):
        if self.equivalent(parent, candidate):
            return 0.0, Decision(False, 0.0), "duplicate"
        a, b = dict(parent.assessment.metrics), dict(candidate.assessment.metrics)
        delta = (
            b["target_overflow"]
            - a["target_overflow"]
            + 0.5 * (b["area"] / (1 + b["area"]) - a["area"] / (1 + a["area"]))
        ) / self.normalizer
        if delta == 0:
            delta = 0.000001 * (
                b["wire_path_cells"] / (1 + b["wire_path_cells"])
                - a["wire_path_cells"] / (1 + a["wire_path_cells"])
            )
        decision = decide(self.method, delta, heat, self.accept_rng)
        return delta, decision, "accepted" if decision.accepted else "rejected"
