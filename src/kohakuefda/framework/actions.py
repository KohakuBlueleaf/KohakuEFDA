"""Builtin action handlers over the public transaction workspace."""

from typing import Protocol

from kohakuefda.model.solver import Action, Anchor, WorldView


class Workspace(Protocol):
    """Temporary edit surface; the context owns rollback and publication."""

    @property
    def view(self) -> WorldView: ...
    def put(self, block_id: str, anchor: Anchor) -> None: ...
    def remove(self, block_id: str) -> None: ...
    def reroute(self, routes: tuple[str, ...]) -> None: ...
    def check(self) -> None: ...


class ActionHandler(Protocol):
    def __call__(self, workspace: Workspace, action: Action) -> None: ...


def relocate(workspace: Workspace, action: Action) -> None:
    """Replace named machines, routing their affected connections as they stand."""
    for block_id, _ in action.anchors:
        workspace.remove(block_id)
    for block_id, anchor in action.anchors:
        workspace.put(block_id, anchor)


def rebuild(workspace: Workspace, action: Action) -> None:
    """Reconstruct all supplied anchors in order, with placement and routing coupled."""
    for block_id, _ in workspace.view.anchors:
        workspace.remove(block_id)
    anchors = dict(action.anchors)
    for block_id in action.order or tuple(anchors):
        workspace.put(block_id, anchors[block_id])


def reroute(workspace: Workspace, action: Action) -> None:
    """Release the selected routes and their dependants and reconnect them."""
    workspace.reroute(action.routes)


def default_actions() -> dict[str, ActionHandler]:
    return {"relocate": relocate, "rebuild": rebuild, "reroute": reroute}
