"""Solver-independent sampled progress frames over retained physical realizations."""

from kohakuefda.model.solver import Snapshot

FRAME_SCHEMA = 1
FRAME_SECONDS = 1.0
PHASES = {
    "build": "construction",
    "improve": "improvement",
    "final": "final",
    "selected": "final",
}


def summary(snapshot: Snapshot | None) -> dict | None:
    """Describe assessed evidence without conflating workspace and target validity."""
    if snapshot is None:
        return None
    workspace = snapshot.backend.startswith("site-workspace-")
    metrics = dict(snapshot.assessment.metrics)
    return {
        "state_id": snapshot.id,
        "domain": "workspace" if workspace else "target",
        "missing": sum(i.rule == "layout.unplaced" for i in snapshot.assessment.issues),
        "complete": snapshot.assessment.complete,
        "routed": snapshot.assessment.routed and not workspace,
        "workspace_routed": bool(
            metrics.get(
                "workspace_routed", snapshot.assessment.routed if workspace else False
            )
        ),
        "geometry": snapshot.assessment.geometry,
        "routing": snapshot.assessment.routing,
        "rates": snapshot.assessment.rates,
        "terms": metrics,
    }


class Progress:
    """Sample at safe solver boundaries; milestones bypass periodic frame suppression."""

    def __init__(self, context):
        self.context = context
        self.calls = 0
        self.last_time = 0.0
        self.last_phase = None
        self.last_snapshot = None

    def send(self, kind, *, snapshot=None, best=None, force=False, **fields):
        ctx = self.context
        if ctx.observe is None:
            return
        self.calls += 1
        every = int(ctx.world_settings["frame_every"])
        phase = fields.get("phase", PHASES.get(kind, kind))
        elapsed = ctx.budget.elapsed
        if not force and (
            not every
            or not (
                self.last_phase != phase
                or self.calls % every == 0
                or elapsed - self.last_time >= FRAME_SECONDS
            )
        ):
            return
        snapshot = snapshot or ctx.current or ctx._backend.capture()
        best = best or ctx.best_routed or ctx.diagnostic
        frame = ctx._backend.snapshot_frame(snapshot, kind)
        frame.update(
            frame_schema=FRAME_SCHEMA,
            phase=phase,
            solver=getattr(ctx, "solver_name", ""),
            elapsed=elapsed,
            work=dict(ctx.budget.work),
            best=summary(best),
            display="current",
            **{k: v for k, v in fields.items() if k != "phase"},
        )
        self.last_time, self.last_phase = elapsed, phase
        self.last_snapshot = snapshot
        ctx.emit(kind, frame)
