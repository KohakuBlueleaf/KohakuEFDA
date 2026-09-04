"""Table port records map onto grid cells and edges by flow heading."""

import pytest

from kohakuefda.data.normalize.ports import PortMappingError, map_port
from kohakuefda.model.geometry import Edge
from kohakuefda.model.machines import GROUND, SKY, PortDir, PortType


def raw(x: int, z: int, heading: int, is_pipe: bool = False) -> dict:
    return {
        "index": "0",
        "isPipe": is_pipe,
        "trans": {
            "position": {"x": str(x), "y": "3" if is_pipe else "0", "z": str(z)},
            "rotation": {"x": "0", "y": str(heading), "z": "0"},
        },
    }


def test_refining_unit_pattern() -> None:
    belt_in = map_port(raw(1, 2, 180), 0, PortDir.IN, 3, 3, False, "t")
    assert (belt_in.x, belt_in.y, belt_in.edge, belt_in.layer) == (1, 0, Edge.N, GROUND)
    belt_out = map_port(raw(1, 0, 180), 0, PortDir.OUT, 3, 3, False, "t")
    assert (belt_out.x, belt_out.y, belt_out.edge) == (1, 2, Edge.S)
    pipe_in = map_port(raw(0, 1, 90, True), 3, PortDir.IN, 3, 3, True, "t")
    assert (pipe_in.x, pipe_in.y, pipe_in.edge, pipe_in.layer) == (0, 1, Edge.W, SKY)
    assert pipe_in.type is PortType.PIPE
    pipe_out = map_port(raw(2, 1, 90, True), 3, PortDir.OUT, 3, 3, True, "t")
    assert (pipe_out.x, pipe_out.y, pipe_out.edge) == (2, 1, Edge.E)


def test_hub_pattern_uses_all_four_headings() -> None:
    assert map_port(raw(8, 4, 90), 0, PortDir.OUT, 9, 9, False, "hub").edge is Edge.E
    assert map_port(raw(0, 4, 270), 0, PortDir.OUT, 9, 9, False, "hub").edge is Edge.W
    assert map_port(raw(4, 0, 0), 0, PortDir.IN, 9, 9, False, "hub").edge is Edge.S
    assert map_port(raw(4, 8, 180), 0, PortDir.IN, 9, 9, False, "hub").edge is Edge.N


def test_interior_port_is_rejected() -> None:
    with pytest.raises(PortMappingError):
        map_port(raw(1, 1, 180), 0, PortDir.IN, 3, 3, False, "t")
