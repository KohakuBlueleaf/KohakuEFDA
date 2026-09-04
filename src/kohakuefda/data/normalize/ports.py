"""Table port transforms → grid ports.

Grid convention: machine-local cell (0, 0) is the top-left, x grows right, y grows down. The
table's ``position.x`` is the local x; ``position.z`` counts from the bottom, so
``y = depth - 1 - z``. ``rotation.y`` is the flow heading (0 = up/N, 90 = E, 180 = down/S,
270 = W): an input port sits on the edge opposite its heading, an output on the edge it heads to.
"""

from kohakuefda.model.geometry import Edge
from kohakuefda.model.machines import GROUND, SKY, Port, PortDir, PortType

HEADING_EDGE = {0: Edge.N, 90: Edge.E, 180: Edge.S, 270: Edge.W}
OPPOSITE = {Edge.N: Edge.S, Edge.S: Edge.N, Edge.E: Edge.W, Edge.W: Edge.E}


class PortMappingError(ValueError):
    """A mapped port does not lie on the footprint edge it faces."""


def on_edge(x: int, y: int, width: int, depth: int, edge: Edge) -> bool:
    match edge:
        case Edge.N:
            return y == 0
        case Edge.S:
            return y == depth - 1
        case Edge.W:
            return x == 0
        case Edge.E:
            return x == width - 1
    return False


def map_port(
    raw: dict,
    index: int,
    direction: PortDir,
    width: int,
    depth: int,
    is_pipe: bool,
    owner: str,
) -> Port:
    """Build a grid ``Port`` from a table port record; raises when it is not on its edge."""
    trans = raw.get("trans", raw)
    pos = trans["position"]
    heading = int(float(trans["rotation"]["y"])) % 360
    x = int(float(pos["x"]))
    y = depth - 1 - int(float(pos["z"]))
    facing = HEADING_EDGE[heading]
    edge = facing if direction is PortDir.OUT else OPPOSITE[facing]
    if not on_edge(x, y, width, depth, edge):
        raise PortMappingError(
            f"{owner} port {index} at ({x},{y}) is not on edge {edge}"
        )
    return Port(
        index=index,
        direction=direction,
        type=PortType.PIPE if is_pipe else PortType.BELT,
        x=x,
        y=y,
        edge=edge,
        layer=SKY if is_pipe else GROUND,
    )
