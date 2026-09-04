"""Rotation helpers keep ports on the edge they face."""

from kohakuefda.data.normalize.ports import on_edge
from kohakuefda.model.geometry import (
    ROTATIONS,
    Edge,
    edge_step,
    rotate_cell,
    rotate_edge,
    rotated_size,
)
from kohakuefda.model.machines import Port, PortDir, PortType


def test_four_quarter_turns_are_identity() -> None:
    for x, y in ((0, 0), (2, 1), (5, 3)):
        cx, cy, w, d = x, y, 6, 4
        for _ in range(4):
            cx, cy = rotate_cell(cx, cy, w, d, 90)
            w, d = d, w
        assert (cx, cy) == (x, y)
    assert rotate_cell(0, 0, 6, 4, 90) == (3, 0)
    assert rotate_cell(5, 3, 6, 4, 180) == (0, 0)
    assert rotate_edge(Edge.N, 360) is Edge.N


def test_rotated_port_stays_on_its_edge() -> None:
    port = Port(
        index=0, direction=PortDir.IN, type=PortType.BELT, x=1, y=0, edge=Edge.N
    )
    width, depth = 3, 5
    for rotation in ROTATIONS:
        rotated = port.rotated(width, depth, rotation)
        w, d = rotated_size(width, depth, rotation)
        assert on_edge(rotated.x, rotated.y, w, d, rotated.edge)
    assert port.rotated(width, depth, 90).edge is Edge.E
    assert port.rotated(width, depth, 180).edge is Edge.S


def test_edge_step_points_outward() -> None:
    assert edge_step(Edge.N) == (0, -1)
    assert edge_step(Edge.S) == (0, 1)
    assert edge_step(Edge.E) == (1, 0)
    assert edge_step(Edge.W) == (-1, 0)
