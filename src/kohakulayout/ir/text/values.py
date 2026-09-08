"""Typing the VALUE tokens of the text form, and writing values back."""

from fractions import Fraction
from typing import Any

from kohakulayout.ir.base import rate_text

Scalar = int | Fraction | bool | str


def parse_scalar(token: str, rates: bool = True) -> Scalar:
    if token == "true":
        return True
    if token == "false":
        return False
    if token.lstrip("-").isdigit():
        return int(token)
    parts = token.split("/")
    if rates and len(parts) == 2 and all(p.isdigit() for p in parts):
        return Fraction(int(parts[0]), int(parts[1]))
    return token


def parse_value(token: str, rates: bool = True) -> Any:
    """A scalar, or a list of scalars when the token holds commas; ``rates`` types ``n/d`` as a Fraction."""
    if "," in token:
        return [parse_scalar(part, rates) for part in token.split(",") if part != ""]
    return parse_scalar(token, rates)


def unquote(token: str) -> str:
    body = token[1:-1]
    return body.encode("utf-8").decode("unicode_escape") if "\\" in body else body


def quote(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def write_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Fraction):
        return str(value.numerator) if value.denominator == 1 else rate_text(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        if (
            value == ""
            or any(ch in value for ch in ' \t;{}#",')
            or value in ("true", "false")
        ):
            return quote(value)
        if value.lstrip("-").isdigit():
            return quote(value)
        return value
    raise TypeError(f"not a text-form scalar: {value!r}")


def write_value(value: Any) -> str:
    if isinstance(value, list | tuple):
        return ",".join(write_scalar(v) for v in value)
    return write_scalar(value)
