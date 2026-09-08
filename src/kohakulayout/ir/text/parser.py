"""The Lark entry point: the lazily built parser, and ``parse_text`` from text to levels."""

import pathlib

import lark
import lark.exceptions

from kohakulayout._rust_bridge import rust_parse_kl
from kohakulayout.errors import TextError
from kohakulayout.ir.text.assemble import Levels, assemble, levels_from_json
from kohakulayout.ir.text.transformer import KlTransformer

GRAMMAR_PATH = pathlib.Path(__file__).with_name("kl.lark")
_parser: lark.Lark | None = None


def grammar() -> lark.Lark:
    global _parser
    if _parser is None:
        _parser = lark.Lark(
            GRAMMAR_PATH.read_text(encoding="utf-8"),
            parser="lalr",
            lexer="contextual",
            propagate_positions=True,
        )
    return _parser


def parse_statements(text: str) -> list:
    """The statement list of ``text``, or :class:`TextError` naming the line."""
    if not text.endswith("\n"):
        text += "\n"
    try:
        tree = grammar().parse(text)
    except lark.exceptions.UnexpectedInput as exc:
        lines = text.splitlines()
        line = lines[exc.line - 1] if 0 < exc.line <= len(lines) else ""
        raise TextError(
            f"line {exc.line}, column {exc.column}: {exc.__class__.__name__}: {line.strip()}"
        ) from exc
    return KlTransformer().transform(tree)


def parse_text(text: str, context: Levels | None = None) -> Levels:
    """Every level the text holds, assembled; ``context`` supplies what a layout refers to.

    The native twin parses first when it is built; its answer is the same by the parity suite.
    """
    context_json = None
    if context is not None:
        problem = context.problem
        context_json = (
            problem.to_json()
            if problem is not None
            else (context.netlist.to_json() if context.netlist is not None else None)
        )
    native = rust_parse_kl(text, context_json)
    if native is not None:
        return levels_from_json(native)
    return assemble(parse_statements(text), context)
