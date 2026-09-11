"""Stage 4 for Endfield: what every machine takes and makes, read from its flow facts.

A splitter divides evenly over the outputs that accept (JCT-01); a converger with one
input lets it bring what the outlet takes and with several lets each bring its capacity
(JCT-02, JCT-03); a control port passes its one item (JCT-05); a conduit inlet hands what
it takes to its linked outlet (DEP-16). A cell's ``role`` fact names its machine: a
crafter runs at the least-fed input, stalls under its activation minimum (ACT-01), takes
what its recipe consumes, and makes what its outlets accept; a source makes its item at
its rate; a depot sink takes everything and its depot ports make what its config names
(DEP-02); a dump takes its items at its rate; a gas unit takes the zone rate (ENV-01);
an entry makes its fluid at its rate. Each pin demands what the plan routed on it; the
pack's evaluator is ``routed`` and assessments do not run it.
"""

from fractions import Fraction
from typing import Any

from kohakuefda.physics.facts import facts, pin_facts
from kohakuefda.physics.library import BRIDGE
from kohakulayout.physics import DefaultFlow, Made

LINK = "link"
Mix = dict[str, Fraction]


def _total(mix: Mix) -> Fraction:
    return sum(mix.values(), Fraction(0))


def _merge(mixes: list[Mix]) -> Mix:
    out: Mix = {}
    for mix in mixes:
        for key, rate in mix.items():
            if rate > 0:
                out[key] = out.get(key, Fraction(0)) + rate
    return out


def rated(entries: Any) -> dict[str, Fraction]:
    """``item:rate/min`` entries as a mapping."""
    out: dict[str, Fraction] = {}
    for entry in entries or ():
        item, rate = str(entry).split(":")
        out[item] = Fraction(rate.removesuffix("/min"))
    return out


def activation_of(cell: Any) -> tuple[str, Fraction, Fraction] | None:
    """The activation item, its minimum and its maximum, from the ``activation`` fact."""
    text = facts(cell).get("activation")
    if not text:
        return None
    item, low, high = str(text).split(":")
    return item, Fraction(low.removesuffix("/min")), Fraction(high.removesuffix("/min"))


class EndfieldFlow(DefaultFlow):
    evaluates = False
    evaluator = "routed"

    def stateful(self) -> bool:
        return True

    def demand(self, cell: Any, pin: str) -> Fraction | None:
        found = pin_facts(cell).get(pin)
        return None if found is None else found[1]

    def commodity(self, cell: Any, pin: str) -> str:
        found = pin_facts(cell).get(pin)
        return found[0] if found and found[0] else f"{cell.id}.{pin}"

    def links(self, netlist: Any) -> tuple[tuple[str, str, str, str], ...]:
        out = []
        for link in facts(netlist).get("links", ()):
            inlet, outlet = str(link).split(":")
            out.append((inlet, LINK, outlet, LINK))
        return tuple(out)

    def passes(self, unit: Any, commodity: str) -> bool:
        wanted = facts(unit).get("item")
        return not wanted or commodity == wanted

    def crosses(self, unit: Any) -> bool:
        return unit.footprint in BRIDGE.values()

    def merge_accept(
        self, capacities: tuple[Fraction, ...], outlet: Fraction
    ) -> tuple[Fraction, ...]:
        if len(capacities) == 1:
            return (min(capacities[0], outlet),)
        return tuple(capacities)

    # ------------------------------------------------------------ cells
    def accept(
        self,
        cell: Any,
        seen: dict[str, frozenset[str]],
        capacities: dict[str, Fraction],
        room: dict[str, Fraction],
    ) -> dict[str, Fraction]:
        role = facts(cell).get("role", "")
        pins = pin_facts(cell)
        if role == "crafter":
            return self.crafter_accepts(cell, seen, capacities)
        if role == "dump":
            treats = set(facts(cell).get("accepts", ()))
            return {
                pin: (
                    Fraction(0)
                    if seen[pin] and not (seen[pin] & treats)
                    else min(capacities[pin], pins[pin][1])
                )
                for pin in capacities
            }
        if role == "zone":
            return {pin: min(capacities[pin], pins[pin][1]) for pin in capacities}
        if role == "inlet":
            wanted = facts(cell).get("filter", "")
            limit = room.get(LINK)
            return {
                pin: (
                    Fraction(0)
                    if wanted and seen[pin] and wanted not in seen[pin]
                    else (
                        capacities[pin]
                        if limit is None
                        else min(capacities[pin], limit)
                    )
                )
                for pin in capacities
            }
        if role == "outlet":
            return {
                pin: (
                    sum(room.values(), Fraction(0)) if pin == LINK else capacities[pin]
                )
                for pin in capacities
            }
        return dict(capacities)

    def crafter_accepts(
        self,
        cell: Any,
        seen: dict[str, frozenset[str]],
        capacities: dict[str, Fraction],
    ) -> dict[str, Fraction]:
        """Each in pin takes the recipe's rate of every item it has seen, split over the pins that saw it; activation up to its cap."""
        need = rated(facts(cell).get("needs"))
        activation = activation_of(cell)
        carriers: dict[str, int] = {}
        for items in seen.values():
            for item in items:
                carriers[item] = carriers.get(item, 0) + 1
        out: dict[str, Fraction] = {}
        for pin, capacity in capacities.items():
            carried = seen[pin]
            if not carried:
                out[pin] = capacity
                continue
            total = Fraction(0)
            for item in carried:
                if activation and item == activation[0]:
                    total += activation[2]
                else:
                    total += need.get(item, Fraction(0)) / carriers[item]
            out[pin] = min(capacity, total)
        return out

    def produce(
        self, cell: Any, inputs: dict[str, Mix], accepts: dict[str, Fraction]
    ) -> Made | None:
        role = facts(cell).get("role", "")
        pins = pin_facts(cell)
        arrived = _merge(list(inputs.values()))
        if role == "crafter":
            return self.crafter_makes(cell, inputs, accepts)
        if role in ("source", "entry", "sink"):
            outputs: dict[str, Mix] = {}
            made: Mix = {}
            for pin in accepts:
                item, rate = pins.get(pin, ("", Fraction(0)))
                if item and rate > 0:
                    outputs[pin] = {item: rate}
                    made[item] = max(made.get(item, Fraction(0)), rate)
            if role == "source":
                return Made(
                    outputs=self.spread(outputs, accepts),
                    made=made,
                    load=Fraction(1) if made else Fraction(0),
                    note="" if made else "no item chosen",
                )
            return Made(outputs=outputs, made=made, load=Fraction(1))
        if role in ("dump", "zone"):
            rate = next((r for _, r in pins.values() if r > 0), Fraction(1))
            return Made(
                outputs={},
                load=min(Fraction(1), _total(arrived) / rate),
                note="" if arrived or role == "dump" else "no gas",
            )
        if role == "inlet":
            wanted = facts(cell).get("filter", "")
            kept = {k: v for k, v in arrived.items() if not wanted or k == wanted}
            return Made(
                outputs={LINK: kept},
                made={},
                load=Fraction(1) if kept else Fraction(0),
                note="" if kept else "nothing received",
            )
        if role == "outlet":
            got = dict(inputs.get(LINK, {}))
            linked = LINK in inputs
            return Made(
                outputs=self.spread({pin: got for pin in accepts}, accepts, once=True),
                made=got,
                load=Fraction(1) if got else Fraction(0),
                note="" if linked else "no conduit link",
            )
        return None

    def spread(
        self, outputs: dict[str, Mix], accepts: dict[str, Fraction], once: bool = False
    ) -> dict[str, Mix]:
        """Each item shared over the out pins that carry it, by what they accept; ``once`` shares one mix over every pin."""
        by_item: dict[str, tuple[Fraction, list[str]]] = {}
        for pin, mix in outputs.items():
            for item, rate in mix.items():
                total, pins = by_item.setdefault(item, (Fraction(0), []))
                by_item[item] = (rate if once else total + rate, [*pins, pin])
        out: dict[str, Mix] = {pin: {} for pin in outputs}
        for item, (rate, pins) in by_item.items():
            shares = self.share(rate, tuple(accepts.get(p, Fraction(0)) for p in pins))
            for pin, share in zip(pins, shares, strict=True):
                if share > 0:
                    out[pin][item] = share
        return out

    def crafter_makes(
        self, cell: Any, inputs: dict[str, Mix], accepts: dict[str, Fraction]
    ) -> Made:
        """The recipe at the least-fed input, stalled under activation, capped by what the outlets of each product accept."""
        pins = pin_facts(cell)
        if not facts(cell).get("recipe"):
            return Made(outputs={}, load=Fraction(0), note="no recipe")
        arrived = _merge(list(inputs.values()))
        need = rated(facts(cell).get("needs"))
        product = rated(facts(cell).get("makes"))
        util = Fraction(1)
        stalled = ""
        activation = activation_of(cell)
        for item, rate in need.items():
            if activation and item == activation[0]:
                continue
            have = arrived.get(item, Fraction(0))
            if have < rate * util:
                util = have / rate if rate else util
                if util == 0:
                    stalled = f"no {item}"
        if activation and arrived.get(activation[0], Fraction(0)) < activation[1]:
            util = Fraction(0)
            stalled = f"activation {activation[0]} below {activation[1]}/min"
        outlets = {
            item: [pin for pin in accepts if pins.get(pin, ("", 0))[0] == item]
            for item in product
        }
        for item, rate in product.items():
            accepted = sum((accepts[p] for p in outlets[item]), Fraction(0))
            if accepted < rate * util:
                util = accepted / rate if rate else util
                if util == 0:
                    stalled = f"no outlet for {item}"
        outputs = {
            pin: {item: rate * util}
            for pin in accepts
            for item, rate in product.items()
            if pins.get(pin, ("", 0))[0] == item
        }
        return Made(
            outputs=self.spread(outputs, accepts, once=True),
            made={item: rate * util for item, rate in product.items()},
            load=util,
            note=stalled,
        )


__all__ = ["LINK", "EndfieldFlow", "activation_of", "rated"]
