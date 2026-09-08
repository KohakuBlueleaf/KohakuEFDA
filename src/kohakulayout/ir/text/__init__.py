"""The text form: the Lark grammar, the parser, the assembler and the writer, registered as the level codec."""

from kohakulayout.ir.base import register_text_codec
from kohakulayout.ir.text.assemble import Levels
from kohakulayout.ir.text.parser import parse_statements, parse_text
from kohakulayout.ir.text.writer import write


def _parse_for(text: str, cls: type):
    return parse_text(text).pick(cls)


register_text_codec(write, _parse_for)

__all__ = ["Levels", "parse_statements", "parse_text", "write"]
