"""B*-tree neighborhoods over retained coupled physical realizations."""

import json
from dataclasses import asdict

from kohakuefda.framework.control import ConfigurationError, Rejected
from kohakuefda.model.solver import Action, Scope
from kohakuefda.solvers.local.decode import TreeDecoder, workspace_place
from kohakuefda.solvers.local.moves import ConstructionMoves, LayoutMoves
from kohakuefda.solvers.local.search import Trajectory
from kohakuefda.solvers.local.tree import FloorTree, initial_tree

ACTION = "local.tree"
DEFAULTS = {
    "tree_every": 4,
    "tree_gap": 2,
    "tree_max_gap": 4,
    "tree_candidates": 150,
    "tree_pull": 0.5,
    "tree_clearance": 2,
    "tree_rebuild": False,
    "tree_warm_start": True,
    "tree_relative": True,
    "tree_improvement": False,
}


class TreeState:
    """Retain structural and physical ancestry together across accepted proposals."""

    def __init__(self, context, settings):
        self.context, self.settings = context, settings
        self.decoder = TreeDecoder(context, settings)
        self.rng = context.rng("tree.proposals")
        self.current = initial_tree(
            context.blocks, self.decoder.order(), context.area, settings["tree_gap"]
        )
        self.parent = self.candidate = self.current
        self.before = {}
        self.changed = ()
        self.active = False
        self.hints = {}

    def begin(self, mutate=True):
        self.parent = self.candidate = self.current
        self.before = dict(self.context.anchors)
        self.changed = ()
        self.active = mutate
        if not mutate:
            return "physical"
        operator, self.candidate = self.current.mutate(
            self.rng, self.settings["tree_max_gap"]
        )
        old = self.current.pack(self.context.blocks, self.context.area)
        new = self.candidate.pack(self.context.blocks, self.context.area)
        self.changed = tuple(i for i in old if old[i] != new[i])
        self.hints = dict(new)
        if self.settings["tree_relative"]:
            for i, (x, y, r) in self.before.items():
                if i in new:
                    ox, oy, orientation = old[i]
                    nx, ny, rotation = new[i]
                    self.hints[i] = (
                        x + nx - ox,
                        y + ny - oy,
                        (r + rotation - orientation) % 360,
                    )
        return f"tree.{operator}"

    def accept(self):
        if self.active:
            self.current = self.candidate

    def removed(self):
        return (
            tuple(self.before)
            if self.settings["tree_rebuild"]
            else tuple(i for i in self.changed if i in self.before)
        )

    def evidence(self, candidate=None):
        after = dict(json.loads(candidate.payload)["anchors"]) if candidate else None
        return {
            "representation": "btree",
            "tree_parent": self.parent.id,
            "tree_candidate": self.candidate.id,
            "tree_next": self.current.id,
            "tree_changed_targets": len(self.changed),
            "tree_realized_changes": (
                sum(
                    tuple(after[i]) != anchor
                    for i, anchor in self.before.items()
                    if i in after
                )
                if after is not None
                else None
            ),
            "tree_added": (
                len(after.keys() - self.before.keys()) if after is not None else None
            ),
            "tree_removed": (
                len(self.before.keys() - after.keys()) if after is not None else None
            ),
            "tree_hints": self.hints if self.active else None,
            "tree_model": asdict(self.candidate) if self.active else None,
        }


class TreeConstruction(ConstructionMoves):
    def __init__(self, context, settings, state):
        super().__init__(context, settings)
        self.state = state
        self.structural = not settings["tree_warm_start"]

    def prepare(self, step):
        self.structural = step % self.settings["tree_every"] == 0
        operator = self.state.begin(self.structural)
        if not self.structural:
            return super().prepare(step)
        result = self.repair.builder.withdraw(self.state.removed())
        if result.status != "removed":
            raise Rejected(result.message, result.status)
        return operator

    def fill(self, step):
        if self.structural:
            self.state.decoder.run(
                self.state.candidate,
                lambda i, a: self.repair.builder.place(i, a).status == "placed",
                self.state.hints,
            )
        else:
            super().fill(step)

    def accept(self):
        self.state.accept()

    def evidence(self, candidate=None):
        return self.state.evidence(candidate)


class TreeLayout(LayoutMoves):
    def __init__(self, context, settings, state):
        if ACTION in context.actions:
            raise ConfigurationError(f"action already registered: {ACTION}")
        super().__init__(context, settings)
        self.state = state
        self.tree_calls = 0
        self.handler = self.execute
        context.actions[ACTION] = self.handler

    def propose(self):
        self.tree_calls += 1
        active = self.tree_calls % self.settings["tree_every"] == 0
        operator = self.state.begin(active)
        if not active:
            return super().propose()
        removed = self.state.removed()
        if self.state.candidate == self.state.parent:
            return operator, None
        return operator, Action(
            ACTION,
            order=removed,
            scope=Scope(frozenset(removed)),
            options=(
                ("tree", json.dumps(asdict(self.state.candidate))),
                ("hints", json.dumps(self.state.hints)),
            ),
        )

    def execute(self, workspace, action):
        tree = FloorTree.from_json(dict(action.options)["tree"])
        if set(tree.labels) != set(self.state.current.labels):
            raise ConfigurationError("tree labels do not match the physical problem")
        for block_id in action.order:
            workspace.remove(block_id)
        workspace.reroute(workspace.view.unrouted)

        def place(block_id, anchor):
            self.context.budget.charge("actions")
            return workspace_place(workspace, block_id, anchor)

        hints = {
            i: tuple(a) for i, a in json.loads(dict(action.options)["hints"]).items()
        }
        self.state.decoder.run(tree, place, hints)
        if self.context.view.missing or self.context.view.unrouted:
            raise Rejected("tree decoding did not complete placement and routing")

    def accept(self):
        self.state.accept()

    def evidence(self, candidate=None):
        return self.state.evidence(candidate)

    def close(self):
        if self.context.actions.get(ACTION) is self.handler:
            del self.context.actions[ACTION]
        super().close()


class TreeTrajectory(Trajectory):
    """Share HC/SA acceptance while adding structural genotype mutations."""

    def __init__(self, context, settings, method):
        super().__init__(context, settings, method)
        self.tree_state = TreeState(context, settings)

    def equivalent(self, parent, candidate):
        state = self.tree_state
        return super().equivalent(parent, candidate) and (
            not state.active or state.parent == state.candidate
        )

    def construction_moves(self):
        return TreeConstruction(self.context, self.settings, self.tree_state)

    def layout_moves(self):
        if self.settings["tree_improvement"]:
            return TreeLayout(self.context, self.settings, self.tree_state)
        self.tree_state.begin(False)
        return super().layout_moves()
