"""Reading the ``endfield`` attrs: flat scalars and lists of scalars, as the text form holds them.

A pin fact is ``pin:item:rate/min``; a lane fact ``cell:pin:cell:pin:rate/min``; a slot
``x:y:side``; a fixed cell ``x:y``. Rates carry ``/min`` so the text form keeps them as
strings and the digest is the same on both sides. ``pin_facts`` and ``lane_facts`` read a
node once and hand out the same object afterwards; callers read it and never change it.
"""

from collections import OrderedDict
from fractions import Fraction
from typing import Any

from kohakuefda.physics.fabric import NAMESPACE, cell_of, slot_of

PER_MIN = "/min"
MEMO_SIZE = 4096
_PINS: OrderedDict[int, tuple[Any, dict[str, tuple[str, Fraction]]]] = OrderedDict()
_LANES: OrderedDict[int, tuple[Any, list]] = OrderedDict()


def recall(memo: OrderedDict, node: Any) -> Any:
    """The value memoised for this very node, or None."""
    hit = memo.get(id(node))
    return hit[1] if hit is not None and hit[0] is node else None


def remember(memo: OrderedDict, node: Any, value: Any) -> Any:
    """Memoise a value for a node, dropping the oldest past ``MEMO_SIZE``; the value back."""
    memo[id(node)] = (node, value)
    if len(memo) > MEMO_SIZE:
        memo.popitem(last=False)
    return value


def rate_text(rate: Fraction) -> str:
    return f"{rate}{PER_MIN}"


def rate_of(text: str) -> Fraction:
    return Fraction(text.removesuffix(PER_MIN))


def facts(node: Any) -> dict[str, Any]:
    return getattr(node, "attrs", {}).get(NAMESPACE, {})


def pin_fact(pin_id: str, item_id: str, rate: Fraction) -> str:
    return f"{pin_id}:{item_id}:{rate_text(rate)}"


def pin_facts(cell: Any) -> dict[str, tuple[str, Fraction]]:
    """Each pin's item and planned rate, from the cell's ``pins`` facts; read once per cell."""
    hit = recall(_PINS, cell)
    if hit is not None:
        return hit
    out: dict[str, tuple[str, Fraction]] = {}
    for entry in facts(cell).get("pins", ()):
        pin_id, item_id, rate = str(entry).split(":")
        out[pin_id] = (item_id, rate_of(rate))
    return remember(_PINS, cell, out)


def lane_fact(source: tuple[str, str], sink: tuple[str, str], rate: Fraction) -> str:
    return f"{source[0]}:{source[1]}:{sink[0]}:{sink[1]}:{rate_text(rate)}"


def lane_facts(net: Any) -> list[tuple[tuple[str, str], tuple[str, str], Fraction]]:
    """The lanes a framework net carries, ``(source, sink, rate)`` each; read once per net."""
    hit = recall(_LANES, net)
    if hit is not None:
        return hit
    out = []
    for entry in facts(net).get("lanes", ()):
        sc, sp, tc, tp, rate = str(entry).split(":")
        out.append(((sc, sp), (tc, tp), rate_of(rate)))
    return remember(_LANES, net, out)


def cell_text(x: int, y: int) -> str:
    return f"{x}:{y}"


def slot_text(x: int, y: int, side: str) -> str:
    return f"{x}:{y}:{side}"


__all__ = [
    "PER_MIN",
    "cell_of",
    "cell_text",
    "facts",
    "lane_fact",
    "lane_facts",
    "pin_fact",
    "pin_facts",
    "rate_of",
    "rate_text",
    "recall",
    "remember",
    "slot_of",
    "slot_text",
]
