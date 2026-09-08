"""ir/geometry.py: rotations, port and attach cells, contiguity and connectivity."""

from kohakulayout.ir.geometry import (
    attach_cell,
    bbox,
    connected,
    contiguous,
    footprint_cells,
    port_cell,
    rotate_point,
    rotate_side,
    rotate_size,
)


def test_rotation_composes() -> None:
    for px in range(3):
        for py in range(2):
            once = rotate_point(px, py, 3, 2, 90)
            twice = rotate_point(*once, 2, 3, 90)
            assert twice == rotate_point(px, py, 3, 2, 180)
    assert rotate_size(3, 2, 90) == (2, 3)
    assert rotate_side("N", 90) == "E" and rotate_side("W", 90) == "N"


def test_port_and_attach_cells_follow_the_rotation() -> None:
    assert port_cell(3, 3, "W", 0, 0) == (0, 0) and attach_cell(3, 3, "W", 0, 0) == (
        -1,
        0,
    )
    assert port_cell(3, 3, "E", 1, 0) == (2, 1) and attach_cell(3, 3, "E", 1, 0) == (
        3,
        1,
    )
    assert port_cell(3, 3, "N", 2, 90) == (2, 2) and attach_cell(3, 3, "N", 2, 90) == (
        3,
        2,
    )
    assert attach_cell(1, 1, "E", 0, 180) == (-1, 0)


def test_cells_and_paths() -> None:
    assert footprint_cells(2, 3, 2, 1, 90) == ((2, 3), (2, 4))
    assert contiguous(((0, 0), (1, 0), (1, 1))) and not contiguous(((0, 0), (2, 0)))
    assert not contiguous(((0, 0), (1, 0), (0, 0)))
    assert connected(frozenset({(0, 0), (1, 0), (1, 1)})) and not connected(
        frozenset({(0, 0), (2, 0)})
    )
    assert bbox(((2, 3), (4, 5))) == (2, 3, 3, 3)
