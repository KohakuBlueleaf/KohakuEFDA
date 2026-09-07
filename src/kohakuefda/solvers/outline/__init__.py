"""Boundary-relaxed HC/SA: complete routed construction, then fixed-outline search."""

from kohakuefda.framework.control import ConfigurationError
from kohakuefda.framework.workspace import Workspace
from kohakuefda.solvers.local import DEFAULTS as LOCAL_DEFAULTS
from kohakuefda.solvers.local import LocalSolver
from kohakuefda.solvers.local.search import Trajectory
from kohakuefda.solvers.outline.search import OutlineTrajectory

DEFAULTS = {
    **LOCAL_DEFAULTS,
    "workspace_extra": 20,
    "workspace_growth": 20,
    "workspace_max_extra": 60,
    "workspace_steps": 48,
    "outline_radius": 6,
}


class OutlineSolver(LocalSolver):
    """Retain oversized evidence separately; only target-board reassessment publishes."""

    defaults = DEFAULTS

    def __init__(self, **settings):
        super().__init__(**settings)
        for key in (
            "workspace_extra",
            "workspace_growth",
            "workspace_steps",
            "outline_radius",
        ):
            if self.settings[key] < 1:
                raise ConfigurationError(f"{key} must be positive")
        if (
            not self.settings["workspace_extra"]
            <= self.settings["workspace_max_extra"]
            <= 256
        ):
            raise ConfigurationError("workspace requires extra <= max_extra <= 256")

    def solve(self, context):
        if context.current is not None:
            Trajectory(context, self.settings, self.method).improve()
            return "completed"
        previous = None
        for extra in range(
            self.settings["workspace_extra"],
            self.settings["workspace_max_extra"] + 1,
            self.settings["workspace_growth"],
        ):
            workspace = Workspace(context, extra)
            if previous is not None:
                workspace.transfer(previous)
            settings = {
                **self.settings,
                "until_budget": False,
                "construction_steps": min(
                    self.settings["construction_steps"],
                    self.settings["workspace_steps"],
                ),
            }
            trajectory = Trajectory(workspace.context, settings, self.method)
            if trajectory.construct():
                if context.current is None:
                    OutlineTrajectory(workspace, self.settings, self.method).improve()
                return "completed" if context.best_routed else "no_solution_found"
            previous = workspace.context.diagnostic
        return "no_solution_found"


class OutlineHillClimbing(OutlineSolver):
    name = "hill-climbing-workspace-v1"
    method = "hc"


class OutlineSimulatedAnnealing(OutlineSolver):
    name = "simulated-annealing-workspace-v1"
    method = "sa"
