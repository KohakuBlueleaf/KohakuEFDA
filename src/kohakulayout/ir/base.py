"""The base module every level inherits: nodes, levels, the digest and the level registry.

A level is a pydantic model with ``extra="forbid"``; ids are strings; ``attrs`` are
namespaced by pack and never read by the framework; rates are exact fractions serialised
as ``"n/d"``. The digest is the SHA-256 of the canonical JSON of the level's canonical
(flat) form, so it is the same whichever form the level was read from.
"""

import hashlib
import json
import re
from collections.abc import Callable
from fractions import Fraction
from typing import Annotated, Any, ClassVar, Self

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    PlainSerializer,
    field_validator,
)

from kohakulayout._rust_bridge import rust_digest
from kohakulayout.errors import IRError

ID_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_/.-]*$")
NAMESPACE_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")
LEVELS: dict[str, type["Level"]] = {}
_TEXT_CODEC: dict[str, Callable] = {}


def parse_rate(value: Any) -> Fraction:
    """A ``Fraction`` from a Fraction, an int, or a ``"n"`` / ``"n/d"`` string."""
    if isinstance(value, Fraction):
        return value
    if isinstance(value, bool):
        raise ValueError("a rate is not a boolean")  # noqa: TRY004
    if isinstance(value, int):
        return Fraction(value)
    if isinstance(value, str):
        return Fraction(value.strip())
    raise ValueError(f"not a rate: {value!r}")


def rate_text(value: Fraction) -> str:
    return f"{value.numerator}/{value.denominator}"


Rate = Annotated[
    Fraction,
    BeforeValidator(parse_rate),
    PlainSerializer(rate_text, return_type=str, when_used="json"),
]
Attrs = dict[str, dict[str, Any]]


class Model(BaseModel):
    """Every IR shape: unknown fields are errors, instances are immutable values."""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)


def check_id(value: str, where: str) -> list[str]:
    if not ID_PATTERN.match(value):
        return [f"{where}: id {value!r} is not an identifier"]
    return []


def check_attrs(attrs: Attrs, where: str) -> list[str]:
    """Every top-level key is a pack namespace holding a dict; nothing else is read."""
    problems = []
    for key, value in attrs.items():
        if not NAMESPACE_PATTERN.match(key):
            problems.append(f"{where}: attrs key {key!r} is not a pack namespace")
        if not isinstance(value, dict):
            problems.append(f"{where}: attrs[{key!r}] is not a dict")
    return problems


class Node(Model):
    """One item with identity: a cell, a net, a group, a unit."""

    id: str
    kind: str = ""
    label: str = ""
    attrs: Attrs = {}

    @field_validator("id")
    @classmethod
    def _id_shape(cls, value: str) -> str:
        if not ID_PATTERN.match(value):
            raise ValueError(f"id {value!r} is not an identifier")
        return value


def jsonable(data: Any) -> Any:
    """Fractions as ``"n/d"``, tuples and sets as lists, recursively: what canonical JSON holds."""
    if isinstance(data, Fraction):
        return rate_text(data)
    if isinstance(data, dict):
        return {str(k): jsonable(v) for k, v in data.items()}
    if isinstance(data, list | tuple):
        return [jsonable(v) for v in data]
    if isinstance(data, set | frozenset):
        return sorted(jsonable(v) for v in data)
    return data


def _json_default(value: Any) -> Any:
    if isinstance(value, Fraction):
        return rate_text(value)
    if isinstance(value, set | frozenset):
        return sorted(jsonable(v) for v in value)
    raise TypeError(f"{type(value).__name__} is not JSON")


def canonical_json(data: Any) -> str:
    """Sorted keys, no whitespace, unicode kept: the bytes every digest is computed on."""
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_json_default,
    )


def digest_of(data: Any) -> str:
    return digest_of_text(canonical_json(data))


def digest_of_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def register_text_codec(writer: Callable, parser: Callable) -> None:
    """Installed by ``kohakulayout.ir.text`` so ``Level.text`` and ``Level.parse`` exist."""
    _TEXT_CODEC["write"] = writer
    _TEXT_CODEC["parse"] = parser


class Level(Model):
    """One stage of the IR: a checkable, printable, hashable document."""

    level: ClassVar[str] = "level"
    schema_version: int = 1

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls.level != "level":
            LEVELS[cls.level] = cls

    def check(self) -> list[str]:
        """Structural problems the framework can see. Empty means well formed."""
        return []

    def verify(self) -> None:
        """Raise :class:`IRError` listing every problem in this level."""
        problems = self.check()
        if problems:
            joined = "\n  ".join(problems)
            raise IRError(f"{self.level} is malformed:\n  {joined}")

    def canonical(self) -> dict[str, Any]:
        """The flat, canonical dict form the digest is computed on. Hierarchy is a view."""
        return {"level": self.level, **jsonable(self.model_dump(mode="python"))}

    def content(self) -> dict[str, Any]:
        """The full dict form the JSON file holds, hierarchy kept."""
        return {"level": self.level, **jsonable(self.model_dump(mode="python"))}

    def digest(self) -> str:
        native = rust_digest(self.to_json())
        return native if native is not None else digest_of(self.canonical())

    def to_json(self) -> str:
        return canonical_json({"level": self.level, **self.model_dump(mode="python")})

    @classmethod
    def from_json(cls, text: str) -> Self:
        data = json.loads(text)
        found = data.pop("level", cls.level)
        if found != cls.level:
            raise IRError(f"expected a {cls.level}, found a {found}")
        return cls.model_validate(data)

    def pretty(self) -> str:
        return json.dumps(self.content(), indent=2, sort_keys=True, ensure_ascii=False)

    def text(self) -> str:
        """The canonical text form, when the text package is loaded."""
        return _TEXT_CODEC["write"](self)

    @classmethod
    def parse(cls, text: str) -> Self:
        found = _TEXT_CODEC["parse"](text, cls)
        if not isinstance(found, cls):
            raise IRError(f"the text holds no {cls.level}")
        return found
