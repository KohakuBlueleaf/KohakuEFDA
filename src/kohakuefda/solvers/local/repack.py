"""Bounded regional reconstruction inside complete-layout action transactions."""

from kohakuefda.framework.control import ConfigurationError, Rejected
from kohakuefda.model.solver import Action, Scope
from kohakuefda.solvers.regional import DEFAULTS as REGIONAL_DEFAULTS
from kohakuefda.solvers.regional.candidates import Proposals

ACTION = "local.repack"


class RepackMoves:
    """Choose a related spatial neighborhood and reconnect it at new anchors."""

    def __init__(self, context, settings, rng) -> None:
        self.context = context
        self.settings = settings
        self.rng = rng
        self.handler = self.execute
        if ACTION in context.actions:
            raise ConfigurationError(f"action already registered: {ACTION}")
        context.actions[ACTION] = self.handler

    def close(self) -> None:
        if self.context.actions.get(ACTION) is self.handler:
            del self.context.actions[ACTION]

    def repack(self) -> Action | None:
        ctx = self.context
        placed = dict(ctx.anchors)
        free = [
            i
            for i in placed
            if ctx.blocks[i].constraint == "free" and not ctx.blocks[i].group
        ]
        if not free:
            return None
        root = self.rng.choice(free)
        x, y, _ = placed[root]
        ordered = sorted(
            free, key=lambda i: abs(placed[i][0] - x) + abs(placed[i][1] - y)
        )
        size = self.rng.randint(2, self.settings["repack_size"])
        selected = ordered[:size]
        self.rng.shuffle(selected)
        return Action(
            ACTION,
            tuple((i, placed[i]) for i in selected),
            scope=Scope(frozenset(selected)),
        )

    def execute(self, workspace, action) -> None:
        ctx = self.context
        ids = [i for i, _ in action.anchors]
        for block_id in ids:
            workspace.remove(block_id)
        workspace.reroute(workspace.view.unrouted)
        proposals = Proposals(
            ctx, {**REGIONAL_DEFAULTS, "candidates": self.settings["repack_candidates"]}
        )
        proposals.reset(self.settings["repack_gap"])
        for block_id in ids:
            anchors = proposals.ranked(block_id, 1, self.rng)
            for anchor in anchors:
                ctx.budget.charge("actions")
                try:
                    workspace.put(block_id, anchor)
                except Rejected as error:
                    if error.status == "scope_required":
                        raise
                    continue
                proposals.occupy(block_id, anchor)
                break
            else:
                raise Rejected(
                    "regional reconstruction did not reconnect every machine"
                )
