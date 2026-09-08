"""A tiny synth for gates: expressions to a netlist, and random circuits by seed.

Expressions: ``y = a & b | ~c``, one per line; ``~`` binds tightest, then ``&``, ``^``, ``|``;
parentheses group. Free names become IN cells on the west edge, targets OUT cells on the east.
"""

import random
import re

from kohakulayout.errors import KohakuLayoutError
from kohakulayout.ir import Cell, Constraint, Net, Netlist, PinRef
from kohakulayout.templates.physics.gates.library import LIBRARY

PACK = "gates"
TOKEN = re.compile(r"\s*(?:([A-Za-z_][A-Za-z0-9_]*)|([&|^~()=]))")
BINARY_OPS = {"&": "AND", "|": "OR", "^": "XOR"}
PRECEDENCE = {"|": 1, "^": 2, "&": 3}


class SynthError(KohakuLayoutError):
    pass


class Builder:
    """Accumulates cells, signals and their sinks; ``netlist`` turns them into L3."""

    def __init__(self) -> None:
        self.cells: dict[str, Cell] = {}
        self.sources: dict[str, PinRef] = {}
        self.sinks: dict[str, list[PinRef]] = {}
        self.count = 0

    def input(self, name: str) -> str:
        if name not in self.cells:
            self.cells[name] = Cell(
                id=name,
                footprint="IN",
                kind="IN",
                constraint=Constraint(kind="edge", attrs={PACK: {"side": "W"}}),
            )
            self.sources[name] = PinRef(cell=name, pin="y")
        return name

    def gate(self, footprint: str, *operands: str) -> str:
        self.count += 1
        cell_id = f"g{self.count}"
        self.cells[cell_id] = Cell(id=cell_id, kind=footprint, footprint=footprint)
        for pin, signal in zip(("a", "b"), operands, strict=False):
            self.sinks.setdefault(signal, []).append(PinRef(cell=cell_id, pin=pin))
        self.sources[cell_id] = PinRef(cell=cell_id, pin="y")
        return cell_id

    def output(self, name: str, signal: str) -> None:
        self.cells[name] = Cell(
            id=name,
            footprint="OUT",
            kind="OUT",
            constraint=Constraint(kind="edge", attrs={PACK: {"side": "E"}}),
        )
        self.sinks.setdefault(signal, []).append(PinRef(cell=name, pin="a"))

    def netlist(self) -> Netlist:
        nets: dict[str, Net] = {}
        for i, (signal, source) in enumerate(sorted(self.sources.items()), start=1):
            sinks = self.sinks.get(signal, [])
            if not sinks:
                continue
            nets[f"n{i}"] = Net(
                id=f"n{i}", carrier="wire", sources=(source,), sinks=tuple(sinks)
            )
        return Netlist(
            pack=PACK, library=dict(LIBRARY), cells=dict(self.cells), nets=nets
        )


def _tokens(text: str) -> list[str]:
    out: list[str] = []
    pos = 0
    while pos < len(text):
        match = TOKEN.match(text, pos)
        if match is None or match.end() == pos:
            raise SynthError(f"cannot read {text[pos:]!r}")
        out.append(match.group(1) or match.group(2))
        pos = match.end()
    return out


class Parser:
    def __init__(self, tokens: list[str], builder: Builder) -> None:
        self.tokens = tokens
        self.pos = 0
        self.builder = builder
        self.signals: dict[str, str] = {}

    def peek(self) -> str | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def take(self) -> str:
        token = self.peek()
        if token is None:
            raise SynthError("unexpected end of expression")
        self.pos += 1
        return token

    def expression(self, min_prec: int = 1) -> str:
        left = self.unary()
        while (op := self.peek()) in PRECEDENCE and PRECEDENCE[op] >= min_prec:
            self.take()
            right = self.expression(PRECEDENCE[op] + 1)
            left = self.builder.gate(BINARY_OPS[op], left, right)
        return left

    def unary(self) -> str:
        token = self.take()
        if token == "~":
            return self.builder.gate("NOT", self.unary())
        if token == "(":
            inner = self.expression()
            if self.take() != ")":
                raise SynthError("expected ')'")
            return inner
        if not token[0].isalpha() and token[0] != "_":
            raise SynthError(f"unexpected {token!r}")
        if token in self.signals:
            return self.signals[token]
        return self.builder.input(token)


def from_expressions(lines: list[str] | str) -> Netlist:
    """A netlist from ``target = expression`` lines; a target may feed later lines as a signal."""
    builder = Builder()
    signals: dict[str, str] = {}
    text = lines if isinstance(lines, str) else "\n".join(lines)
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if "=" not in line:
            raise SynthError(f"expected 'target = expression' in {line!r}")
        target, expr = (part.strip() for part in line.split("=", 1))
        parser = Parser(_tokens(expr), builder)
        parser.signals = signals
        signal = parser.expression()
        if parser.peek() is not None:
            raise SynthError(f"trailing {parser.peek()!r} in {line!r}")
        if (
            signal == target
            or signal in builder.cells
            and builder.cells[signal].footprint == "IN"
        ):
            signal = builder.gate("BUF", signal)
        signals[target] = signal
        builder.output(target, signal)
    return builder.netlist()


def random_circuit(
    seed: int, inputs: int = 4, gates: int = 8, outputs: int = 2
) -> Netlist:
    """A random DAG of two-input gates by seed; the last ``outputs`` gates drive OUT cells."""
    rng = random.Random(seed)
    builder = Builder()
    signals = [builder.input(f"i{n}") for n in range(inputs)]
    for _ in range(gates):
        op = rng.choice(("AND", "OR", "XOR", "NOT"))
        if op == "NOT":
            signals.append(builder.gate(op, rng.choice(signals)))
        else:
            a, b = (
                rng.sample(signals, 2) if len(signals) > 1 else (signals[0], signals[0])
            )
            signals.append(builder.gate(op, a, b))
    gate_ids = [s for s in signals if s.startswith("g")]
    driven = {ref.cell for sinks in builder.sinks.values() for ref in sinks}
    tails = [g for g in gate_ids if g not in driven] or gate_ids[-outputs:]
    for n, signal in enumerate(sorted(set(tails + gate_ids[-outputs:]))):
        builder.output(f"o{n}", signal)
    return builder.netlist()


__all__ = ["Builder", "SynthError", "from_expressions", "random_circuit"]
