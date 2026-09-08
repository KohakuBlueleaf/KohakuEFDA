"""The gates library: footprints of every gate, the jumper unit and the power emitter."""

from kohakulayout.ir import Footprint, Port

FANOUT_LIMIT = 4


def _gate(id: str) -> Footprint:
    return Footprint(
        id=id,
        width=3,
        height=3,
        ports=(
            Port(id="a", side="W", offset=0, direction="in", carrier="wire"),
            Port(id="b", side="W", offset=2, direction="in", carrier="wire"),
            Port(id="y", side="E", offset=1, direction="out", carrier="wire"),
        ),
    )


def _unary(id: str) -> Footprint:
    return Footprint(
        id=id,
        width=2,
        height=3,
        ports=(
            Port(id="a", side="W", offset=1, direction="in", carrier="wire"),
            Port(id="y", side="E", offset=1, direction="out", carrier="wire"),
        ),
    )


LIBRARY: dict[str, Footprint] = {
    "AND": _gate("AND"),
    "OR": _gate("OR"),
    "XOR": _gate("XOR"),
    "NOT": _unary("NOT"),
    "BUF": _unary("BUF"),
    "DFF": Footprint(
        id="DFF",
        width=3,
        height=4,
        ports=(
            Port(id="d", side="W", offset=1, direction="in", carrier="wire"),
            Port(id="q", side="E", offset=1, direction="out", carrier="wire"),
            Port(id="clk", side="S", offset=1, direction="in", carrier="clk"),
        ),
    ),
    "IN": Footprint(
        id="IN",
        width=1,
        height=1,
        ports=(Port(id="y", side="E", offset=0, direction="out", carrier="wire"),),
    ),
    "OUT": Footprint(
        id="OUT",
        width=1,
        height=1,
        ports=(Port(id="a", side="W", offset=0, direction="in", carrier="wire"),),
    ),
}

JUMPER = Footprint(id="JUMPER", width=1, height=1, rotations=(0,))
VDD = Footprint(id="VDD", width=1, height=1, rotations=(0,))

UNARY = frozenset({"NOT", "BUF"})
BINARY = frozenset({"AND", "OR", "XOR"})

__all__ = ["BINARY", "FANOUT_LIMIT", "JUMPER", "LIBRARY", "UNARY", "VDD"]
