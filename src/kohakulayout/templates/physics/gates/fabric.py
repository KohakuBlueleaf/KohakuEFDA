"""The gates fabric: one board from params, two layers, one build region, entries west and east."""

from typing import Any

from kohakulayout.ir import Carrier, Fabric, Region

DEFAULT_WIDTH = 32
DEFAULT_HEIGHT = 16


def fabric(params: dict[str, Any]) -> Fabric:
    width = int(params.get("width", DEFAULT_WIDTH))
    height = int(params.get("height", DEFAULT_HEIGHT))
    every = frozenset((x, y) for y in range(height) for x in range(width))
    return Fabric(
        width=width,
        height=height,
        layers=("ground", "overhead"),
        carriers={
            "wire": Carrier(id="wire", layer="ground"),
            "clk": Carrier(id="clk", layer="overhead"),
        },
        regions={"build": Region.of("build", every)},
        entries=("W", "E"),
    )


__all__ = ["DEFAULT_HEIGHT", "DEFAULT_WIDTH", "fabric"]
