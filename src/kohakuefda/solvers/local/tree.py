"""Immutable B*-tree floorplans and contour packing for coupled search proposals."""

import hashlib
import json
import random
from dataclasses import asdict, dataclass, replace

from kohakuefda.framework.control import ConfigurationError
from kohakuefda.model.solver import Anchor, BlockInfo, Rect


@dataclass(frozen=True)
class FloorTree:
    """Binary packing topology, machine labels, orientations and routing clearances."""

    labels: tuple[str, ...]
    rotations: tuple[int, ...]
    left: tuple[int, ...]
    right: tuple[int, ...]
    gaps: tuple[int, ...]
    root: int = 0

    def __post_init__(self) -> None:
        size = len(self.labels)
        arrays = (self.labels, self.rotations, self.left, self.right, self.gaps)
        if any(type(values) is not tuple or len(values) != size for values in arrays):
            raise ConfigurationError("tree arrays must be immutable and equally sized")
        if len(set(self.labels)) != size or any(
            type(i) is not str for i in self.labels
        ):
            raise ConfigurationError("tree labels must be unique machine identifiers")
        if any(
            type(r) is not int or r not in (0, 90, 180, 270) for r in self.rotations
        ):
            raise ConfigurationError("invalid tree orientation")
        if any(type(gap) is not int or gap < 1 for gap in self.gaps):
            raise ConfigurationError("tree clearances must be positive integers")
        if type(self.root) is not int or not 0 <= self.root < max(1, size):
            raise ConfigurationError("invalid tree root")
        if any(
            type(child) is not int or not -1 <= child < size
            for child in (*self.left, *self.right)
        ):
            raise ConfigurationError("invalid tree child")
        visited = set()
        pending = [self.root] if size else []
        while pending:
            node = pending.pop()
            if node in visited:
                raise ConfigurationError("tree has a cycle or multiple parents")
            visited.add(node)
            pending.extend(
                child for child in (self.left[node], self.right[node]) if child >= 0
            )
        if len(visited) != size:
            raise ConfigurationError("tree contains unreachable nodes")

    @classmethod
    def from_json(cls, text: str) -> "FloorTree":
        try:
            values = json.loads(text)
            if not isinstance(values, dict):
                raise ConfigurationError("tree payload must be an object")
            return cls(
                **{
                    key: tuple(value) if isinstance(value, list) else value
                    for key, value in values.items()
                }
            )
        except (TypeError, ValueError) as error:
            raise ConfigurationError(f"invalid tree payload: {error}") from error

    @property
    def id(self) -> str:
        return hashlib.sha256(
            json.dumps(asdict(self), sort_keys=True).encode()
        ).hexdigest()

    def traversal(self, root: int | None = None) -> tuple[int, ...]:
        if not self.labels:
            return ()
        pending = [self.root if root is None else root]
        visited = []
        while pending:
            node = pending.pop()
            visited.append(node)
            pending.extend(
                child for child in (self.right[node], self.left[node]) if child >= 0
            )
        return tuple(visited)

    def pack(
        self, blocks: dict[str, BlockInfo], area: Rect, obstacles: tuple[Rect, ...] = ()
    ) -> dict[str, Anchor]:
        """Contour pack rectangles; overflow remains explicit rather than clipped away."""
        if not self.labels:
            return {}
        positions = {}
        contour = list(obstacles)
        pending = [(self.root, area[0] + 1)]
        while pending:
            node, x = pending.pop()
            block = blocks[self.labels[node]]
            rotation = self.rotations[node]
            width, height = (
                (block.width, block.height)
                if rotation % 180 == 0
                else (block.height, block.width)
            )
            gap = self.gaps[node]
            y = max(
                [area[1] + 1]
                + [
                    rect[3]
                    for rect in contour
                    if x < rect[2] and x + width + gap > rect[0]
                ]
            )
            positions[self.labels[node]] = (x, y, rotation)
            contour.append((x, y, x + width + gap, y + height + gap))
            if self.right[node] >= 0:
                pending.append((self.right[node], x))
            if self.left[node] >= 0:
                pending.append((self.left[node], x + width + gap))
        return positions

    def mutate(self, rng: random.Random, max_gap: int) -> tuple[str, "FloorTree"]:
        if not self.labels:
            return "empty", self
        operator = rng.choice(("swap", "rotate", "graft", "graft", "gap"))
        n = len(self.labels)
        a = rng.randrange(n)
        if operator == "rotate":
            rotations = list(self.rotations)
            rotations[a] = (rotations[a] + rng.choice((90, 180, 270))) % 360
            return operator, replace(self, rotations=tuple(rotations))
        if operator == "gap":
            gaps = list(self.gaps)
            gaps[a] = rng.randint(1, max_gap)
            return operator, replace(self, gaps=tuple(gaps))
        if n < 2:
            return operator, self
        b = rng.choice([i for i in range(n) if i != a])
        if operator == "swap":
            labels = list(self.labels)
            labels[a], labels[b] = labels[b], labels[a]
            return operator, replace(self, labels=tuple(labels))
        if a == self.root:
            a = b
        subtree = set(self.traversal(a))
        left, right = list(self.left), list(self.right)
        for children in (left, right):
            for parent in range(n):
                if children[parent] == a:
                    children[parent] = -1
        slots = [
            (parent, side)
            for parent in range(n)
            if parent not in subtree
            for side, children in enumerate((left, right))
            if children[parent] < 0
        ]
        parent, side = rng.choice(slots)
        (left, right)[side][parent] = a
        return operator, replace(self, left=tuple(left), right=tuple(right))


def initial_tree(
    blocks: dict[str, BlockInfo], order: tuple[str, ...], area: Rect, gap: int
) -> FloorTree:
    """Initialize shelf-shaped tree topology from a connected-machine ordering."""
    left, right = [-1] * len(order), [-1] * len(order)
    row = previous = 0
    used = 1
    for node, label in enumerate(order):
        width = blocks[label].width + gap
        if node:
            if used + width > area[2] - area[0] - 1:
                right[row] = node
                row, used = node, 1
            else:
                left[previous] = node
        used += width
        previous = node
    return FloorTree(
        order, (0,) * len(order), tuple(left), tuple(right), (gap,) * len(order)
    )
