"""PNG rendering of a layout with matplotlib (optional dependency)."""

import logging
from pathlib import Path

from kohakuefda.layout.geometry import machine_footprint, unit_footprint
from kohakuefda.model.dataset import Dataset
from kohakuefda.model.layout import Layout

log = logging.getLogger(__name__)

try:
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import patches, pyplot
except ImportError:  # optional dependency: `pip install kohakuefda[viz]`
    pyplot = None
    patches = None

MACHINE_COLOR = "#3b6ea5"
UNIT_COLOR = "#8a5a2b"
BELT_COLOR = "#f5d90a"
PIPE_COLOR = "#38b2ac"
ENTRY_COLOR = "#d9480f"


def render_png(
    dataset: Dataset, layout: Layout, path: Path, cell: float = 0.25
) -> Path:
    """Draw footprints, belts, pipes and outside inputs to ``path``; raises ``RuntimeError``
    without matplotlib."""
    if pyplot is None:
        raise RuntimeError("matplotlib is not installed; install kohakuefda[viz]")
    fig, ax = pyplot.subplots(figsize=(layout.width * cell, layout.height * cell))
    ax.set_xlim(0, layout.width)
    ax.set_ylim(layout.height, 0)
    ax.set_aspect("equal")
    ax.set_xticks(range(0, layout.width + 1, 5))
    ax.set_yticks(range(0, layout.height + 1, 5))
    ax.grid(True, linewidth=0.2)
    for placed in layout.machines:
        cells = machine_footprint(dataset, placed)
        xs = [c[0] for c in cells]
        ys = [c[1] for c in cells]
        ax.add_patch(
            patches.Rectangle(
                (min(xs), min(ys)),
                max(xs) - min(xs) + 1,
                max(ys) - min(ys) + 1,
                facecolor=MACHINE_COLOR,
                alpha=0.6,
                edgecolor="black",
            )
        )
        ax.text(
            min(xs) + 0.2,
            min(ys) + 0.9,
            dataset.machines[placed.machine_id].names.en,
            fontsize=5,
            color="white",
        )
    for unit in layout.units:
        for x, y in unit_footprint(dataset, unit):
            ax.add_patch(
                patches.Rectangle((x, y), 1, 1, facecolor=UNIT_COLOR, alpha=0.8)
            )
    for segment in layout.segments:
        color = PIPE_COLOR if segment.kind == "pipe" else BELT_COLOR
        xs = [c[0] + 0.5 for c in segment.cells]
        ys = [c[1] + 0.5 for c in segment.cells]
        ax.plot(xs, ys, color=color, linewidth=2 if segment.kind == "belt" else 3)
    for entry in layout.entries:
        (ox, oy), (ix, iy) = entry.outside, entry.start
        ax.annotate(
            "",
            xy=(ix + 0.5, iy + 0.5),
            xytext=(ox + 0.5, oy + 0.5),
            arrowprops={"arrowstyle": "->", "color": ENTRY_COLOR, "linewidth": 1.5},
        )
        ax.text(
            entry.x + 0.1,
            entry.y + 0.9,
            dataset.items[entry.item_id].names.en,
            fontsize=4,
            color=ENTRY_COLOR,
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    pyplot.close(fig)
    log.info("wrote %s (%dx%d cells)", path, layout.width, layout.height)
    return path
