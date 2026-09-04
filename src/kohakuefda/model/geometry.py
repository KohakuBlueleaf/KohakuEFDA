"""Grid geometry: cells, edges and 90-degree rotations."""

from enum import StrEnum

Rotation = int
ROTATIONS: tuple[Rotation, ...] = (0, 90, 180, 270)


class Edge(StrEnum):
    """Side of a footprint a port faces, in screen orientation (y grows downward)."""

    N = "N"
    E = "E"
    S = "S"
    W = "W"


EDGE_ORDER = (Edge.N, Edge.E, Edge.S, Edge.W)


def rotate_edge(edge: Edge, rotation: Rotation) -> Edge:
    """Edge after rotating a footprint clockwise by ``rotation`` degrees."""
    return EDGE_ORDER[(EDGE_ORDER.index(edge) + rotation // 90) % 4]


def rotate_cell(
    x: int, y: int, width: int, depth: int, rotation: Rotation
) -> tuple[int, int]:
    """Cell (x, y) of a width×depth footprint after a clockwise rotation."""
    match rotation % 360:
        case 0:
            return x, y
        case 90:
            return depth - 1 - y, x
        case 180:
            return width - 1 - x, depth - 1 - y
        case 270:
            return y, width - 1 - x
    raise ValueError(f"rotation must be a multiple of 90, got {rotation}")


def rotated_size(width: int, depth: int, rotation: Rotation) -> tuple[int, int]:
    """Footprint size after rotation."""
    return (width, depth) if rotation % 180 == 0 else (depth, width)


def edge_step(edge: Edge) -> tuple[int, int]:
    """Unit step from a cell across ``edge`` to the neighbouring cell."""
    match edge:
        case Edge.N:
            return 0, -1
        case Edge.E:
            return 1, 0
        case Edge.S:
            return 0, 1
        case Edge.W:
            return -1, 0
    raise ValueError(edge)
