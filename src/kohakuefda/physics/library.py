"""The Endfield units: junctions, bridges and control ports per carrier, and the pylon that emits power.

Belt units stand on the ground; pipe units are pole-supported and take the ground cell too
(LOG-04). A control port lets one item through (JCT-05). A pylon is 2×2 and powers the
12×12 square its footprint extends by five on every side (COV-01); touching the square is
enough (COV-02). A conduit inlet links to an outlet up to 300 cells away (DEP-16).
"""

from kohakulayout.ir import Footprint
from kohakulayout.physics import Emitter, Reach

GROUND = "ground"
SKY = "sky"
BELT = "belt"
PIPE = "pipe"
CARRIERS = (BELT, PIPE)

SPLITTER = {BELT: "log_splitter", PIPE: "log_pipe_splitter"}
CONVERGER = {BELT: "log_converger", PIPE: "log_pipe_converger"}
BRIDGE = {BELT: "log_connector", PIPE: "log_pipe_connector"}
CONTROL = {BELT: "log_conditioner", PIPE: "log_pipe_conditioner"}
CONDUIT_LINK_MAX = 300
PYLON = "power_diffuser_1"
POWER = "power"
PYLON_REACH = 5
PYLON_SIZE = 2
RUN_LIMIT = {BELT: 110, PIPE: 80}
PIPE_UNIT_LIMIT = 128
FACTS = {
    "endfield": {
        "facts": [
            "LOG-04",
            "LOG-05",
            "LOG-06",
            "JCT-01",
            "JCT-02",
            "JCT-04",
            "JCT-05",
            "COV-01",
            "DEP-16",
        ]
    }
}


def _unit(unit_id: str, carrier: str) -> Footprint:
    return Footprint(
        id=unit_id,
        width=1,
        height=1,
        layer=GROUND if carrier == BELT else SKY,
        occludes=() if carrier == BELT else (GROUND,),
        rotations=(0,),
        attrs={"endfield": {"carrier": carrier, "unit": True}},
    )


UNITS: dict[str, Footprint] = {
    unit_id: _unit(unit_id, carrier)
    for table in (SPLITTER, CONVERGER, BRIDGE, CONTROL)
    for carrier, unit_id in table.items()
}
UNIT_CARRIER: dict[str, str] = {
    unit_id: carrier
    for table in (SPLITTER, CONVERGER, BRIDGE, CONTROL)
    for carrier, unit_id in table.items()
}

PYLON_FOOTPRINT = Footprint(
    id=PYLON,
    width=PYLON_SIZE,
    height=PYLON_SIZE,
    layer=GROUND,
    occludes=(SKY,),
    rotations=(0,),
    attrs={"endfield": {"machine": PYLON, "power": 0, "facts": ["COV-01", "COV-04"]}},
)

PYLON_EMITTER = Emitter(
    kind=POWER,
    footprint=PYLON_FOOTPRINT,
    reach=Reach(
        shape="mask",
        cells=tuple(
            (dx, dy)
            for dy in range(-PYLON_REACH, PYLON_SIZE + PYLON_REACH)
            for dx in range(-PYLON_REACH, PYLON_SIZE + PYLON_REACH)
        ),
        partial=True,
    ),
    overlap="allowed",
)

__all__ = [
    "BELT",
    "BRIDGE",
    "CARRIERS",
    "CONDUIT_LINK_MAX",
    "CONTROL",
    "CONVERGER",
    "FACTS",
    "GROUND",
    "PIPE",
    "PIPE_UNIT_LIMIT",
    "POWER",
    "PYLON",
    "PYLON_EMITTER",
    "PYLON_FOOTPRINT",
    "RUN_LIMIT",
    "SKY",
    "SPLITTER",
    "UNITS",
    "UNIT_CARRIER",
]
