"""Moving fragments: translation, whole-fragment rotation, and dropping them into a layout."""

from kohakuefda.layout.geometry import machine_footprint
from kohakuefda.model.cells import CellInstance, Fragment, Pin
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.geometry import Rotation, rotate_cell, rotate_edge
from kohakuefda.model.layout import Cell, Layout, Placed
from kohakuefda.model.scenario import BasementRef


def _shift(cell: Cell, dx: int, dy: int) -> Cell:
    return (cell[0] + dx, cell[1] + dy)


def translate[T: Fragment](fragment: T, dx: int, dy: int) -> T:
    """The same fragment with every coordinate moved by (dx, dy)."""
    update: dict = {
        "machines": [
            m.model_copy(update={"x": m.x + dx, "y": m.y + dy})
            for m in fragment.machines
        ],
    }
    if isinstance(fragment, CellInstance):
        update["pins"] = [
            p.model_copy(
                update={
                    "cell": _shift(p.cell, dx, dy),
                    "alternatives": [
                        a.model_copy(update={"cell": _shift(a.cell, dx, dy)})
                        for a in p.alternatives
                    ],
                }
            )
            for p in fragment.pins
        ]
    return fragment.model_copy(update=update)


def _rotate_machine(
    dataset: Dataset, placed: Placed, width: int, height: int, rotation: Rotation
) -> Placed:
    cells = [
        rotate_cell(x, y, width, height, rotation)
        for x, y in machine_footprint(dataset, placed)
    ]
    return placed.model_copy(
        update={
            "x": min(c[0] for c in cells),
            "y": min(c[1] for c in cells),
            "rotation": (placed.rotation + rotation) % 360,
        }
    )


def rotate[T: Fragment](dataset: Dataset, fragment: T, rotation: Rotation) -> T:
    """The fragment rotated clockwise as a whole; its box swaps sides for 90 and 270."""
    width, height = fragment.width, fragment.height

    def cell(c: Cell) -> Cell:
        return rotate_cell(c[0], c[1], width, height, rotation)

    def pin(p: Pin) -> Pin:
        return p.model_copy(
            update={
                "cell": cell(p.cell),
                "edge": rotate_edge(p.edge, rotation),
                "alternatives": [
                    a.model_copy(
                        update={
                            "cell": cell(a.cell),
                            "edge": rotate_edge(a.edge, rotation),
                        }
                    )
                    for a in p.alternatives
                ],
            }
        )

    new_width, new_height = (width, height) if rotation % 180 == 0 else (height, width)
    update: dict = {
        "width": new_width,
        "height": new_height,
        "machines": [
            _rotate_machine(dataset, m, width, height, rotation)
            for m in fragment.machines
        ],
    }
    if isinstance(fragment, CellInstance):
        update["pins"] = [pin(p) for p in fragment.pins]
    return fragment.model_copy(update=update)


def fragment_layout(
    fragment: Fragment,
    dataset_version: str,
    basement: BasementRef,
    width: int | None = None,
    height: int | None = None,
) -> Layout:
    """A layout holding just this fragment, in a box at least as large as the fragment."""
    return Layout(
        dataset_version=dataset_version,
        basement=basement,
        width=width or fragment.width,
        height=height or fragment.height,
        machines=list(fragment.machines),
    )


def place(layout: Layout, fragment: Fragment, dx: int, dy: int) -> None:
    """Append the fragment's machines to ``layout`` moved by (dx, dy); ids stay as they are."""
    layout.machines.extend(translate(fragment, dx, dy).machines)
