"""Parse tree to statement records. Each rule becomes one dict with a ``stmt`` key."""

from typing import Any

import lark

from kohakulayout.ir.text.values import parse_value, unquote


def _xy(token: str) -> tuple[int, int]:
    x, y = token.split(",")
    return (int(x), int(y))


def _size(token: str) -> tuple[int, int]:
    w, h = token.split("x")
    return (int(w), int(h))


def _rot(token: str) -> int:
    return int(token[1:])


def _opts(items: list[Any]) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Split transformed children into ``(options, attrs)``; other children are ignored."""
    opts: dict[str, Any] = {}
    attrs: dict[str, dict[str, Any]] = {}
    for item in items:
        if isinstance(item, tuple) and item and item[0] == "opt":
            opts[item[1]] = item[2]
        elif isinstance(item, tuple) and item and item[0] == "attr":
            namespace, key = item[1].split(".", 1)
            attrs.setdefault(namespace, {})[key] = item[2]
    return opts, attrs


def _tokens(items: list[Any], kind: str) -> list[str]:
    return [str(i) for i in items if isinstance(i, lark.Token) and i.type == kind]


class KlTransformer(lark.Transformer):
    """One method per grammar rule; returns plain records the assembler reads."""

    def start(self, items: list[Any]) -> list[dict]:
        return [i for i in items if isinstance(i, dict)]

    def header(self, items: list[Any]) -> dict:
        return {"stmt": "header", "version": int(items[0])}

    def physics(self, items: list[Any]) -> dict:
        return {"stmt": "physics", "id": str(items[0])}

    def fabric(self, items: list[Any]) -> dict:
        opts, attrs = _opts(items[1:])
        return {"stmt": "fabric", "size": _size(items[0]), "opts": opts, "attrs": attrs}

    def region(self, items: list[Any]) -> dict:
        _, attrs = _opts(items[2:])
        return {"stmt": "region", "id": str(items[0]), "expr": items[1], "attrs": attrs}

    def region_all(self, items: list[Any]) -> tuple:
        return ("all",)

    def region_rects(self, items: list[Any]) -> tuple:
        return ("rects", [i for i in items if isinstance(i, tuple) and i[0] == "rect"])

    def region_not(self, items: list[Any]) -> tuple:
        return ("not", str(items[0]))

    def rect(self, items: list[Any]) -> tuple:
        x, y = _xy(items[0])
        w, h = _size(items[1])
        return ("rect", x, y, w, h)

    def carrier(self, items: list[Any]) -> dict:
        rate = None
        rest = items[2:]
        if rest and isinstance(rest[0], lark.Token) and rest[0].type in ("RATE", "INT"):
            rate = parse_value(str(rest[0]))
            rest = rest[1:]
        opts, attrs = _opts(rest)
        return {
            "stmt": "carrier",
            "id": str(items[0]),
            "layer": str(items[1]),
            "capacity": rate,
            "opts": opts,
            "attrs": attrs,
        }

    def param(self, items: list[Any]) -> dict:
        return {"stmt": "param", "key": items[0][1], "value": items[0][2]}

    def cell(self, items: list[Any]) -> dict:
        opts, attrs = _opts(items[2:])
        return {
            "stmt": "cell",
            "id": str(items[0]),
            "ref": str(items[1]),
            "opts": opts,
            "attrs": attrs,
        }

    def pin(self, items: list[Any]) -> dict:
        cell, pin = str(items[0]).split(".", 1)
        opts, _ = _opts(items[3:])
        return {
            "stmt": "pin",
            "cell": cell,
            "pin": pin,
            "direction": str(items[1]),
            "carrier": str(items[2]),
            "opts": opts,
        }

    def net(self, items: list[Any]) -> dict:
        rate = None
        rest = items[2:]
        if rest and isinstance(rest[0], lark.Token) and rest[0].type in ("RATE", "INT"):
            rate = parse_value(str(rest[0]))
            rest = rest[1:]
        opts, attrs = _opts(rest)
        sources = next(i[1] for i in rest if isinstance(i, tuple) and i[0] == "sources")
        sinks = next(i[1] for i in rest if isinstance(i, tuple) and i[0] == "sinks")
        return {
            "stmt": "net",
            "id": str(items[0]),
            "carrier": str(items[1]),
            "rate": rate,
            "opts": opts,
            "attrs": attrs,
            "sources": sources,
            "sinks": sinks,
        }

    def net_sources(self, items: list[Any]) -> tuple:
        return ("sources", [str(i) for i in items])

    def net_sinks(self, items: list[Any]) -> tuple:
        return ("sinks", [str(i) for i in items])

    def group(self, items: list[Any]) -> dict:
        opts, attrs = _opts(items[1:])
        members = _tokens(items[1:], "ID")
        return {
            "stmt": "group",
            "id": str(items[0]),
            "opts": opts,
            "attrs": attrs,
            "members": members,
        }

    def layout_hdr(self, items: list[Any]) -> dict:
        first = items[0] if items else None
        digest = (
            str(first)
            if isinstance(first, lark.Token) and first.type == "DIGEST"
            else ""
        )
        _, attrs = _opts(items)
        return {"stmt": "layout", "digest": digest, "attrs": attrs}

    def netattrs(self, items: list[Any]) -> dict:
        _, attrs = _opts(items)
        return {"stmt": "attrs", "attrs": attrs}

    def place(self, items: list[Any]) -> dict:
        return {
            "stmt": "place",
            "cell": str(items[0]),
            "xy": _xy(items[1]),
            "rot": _rot(items[2]),
        }

    def instance(self, items: list[Any]) -> dict:
        return {
            "stmt": "instance",
            "cell": str(items[0]),
            "xy": _xy(items[1]),
            "rot": _rot(items[2]),
        }

    def wire(self, items: list[Any]) -> dict:
        opts, _ = _opts(items[1:])
        segments = [
            i for i in items[1:] if isinstance(i, dict) and i.get("stmt") == "segment"
        ]
        return {
            "stmt": "wire",
            "net": str(items[0]),
            "opts": opts,
            "segments": segments,
        }

    def segment_moves(self, items: list[Any]) -> dict:
        return {
            "stmt": "segment",
            "start": items[0],
            "moves": list(items[1:-1]),
            "end": items[-1],
        }

    def segment_cells(self, items: list[Any]) -> dict:
        cells = [_xy(i) for i in items[:-1]]
        return {"stmt": "segment", "cells": cells, "end": items[-1]}

    def at_cell(self, items: list[Any]) -> tuple:
        return ("cell", _xy(items[0]))

    def unit(self, items: list[Any]) -> dict:
        opts, attrs = _opts(items[4:])
        return {
            "stmt": "unit",
            "id": str(items[0]),
            "footprint": str(items[1]),
            "xy": _xy(items[2]),
            "rot": _rot(items[3]),
            "opts": opts,
            "attrs": attrs,
        }

    def reserve(self, items: list[Any]) -> dict:
        opts, _ = _opts(items[2:])
        rects = [i for i in items[2:] if isinstance(i, tuple) and i[0] == "rect"]
        return {
            "stmt": "reserve",
            "tag": str(items[0]),
            "layer": str(items[1]),
            "opts": opts,
            "rects": rects,
        }

    def assessment_hdr(self, items: list[Any]) -> dict:
        return {"stmt": "assessment", "digest": str(items[0]) if items else ""}

    def metric(self, items: list[Any]) -> dict:
        return {
            "stmt": "metric",
            "name": str(items[0]),
            "value": parse_value(str(items[1])),
        }

    def finding(self, items: list[Any]) -> dict:
        _, attrs = _opts(items[4:])
        return {
            "stmt": "finding",
            "rule": str(items[0]),
            "severity": str(items[1]),
            "subject": str(items[2]),
            "message": unquote(str(items[3])),
            "attrs": attrs,
        }

    def complete(self, items: list[Any]) -> dict:
        return {"stmt": "complete", "value": str(items[0]) == "true"}

    def valid(self, items: list[Any]) -> dict:
        return {"stmt": "valid", "value": str(items[0]) == "true"}

    def lib(self, items: list[Any]) -> dict:
        opts, attrs = _opts(items[2:])
        ports = [p for i in items[2:] if isinstance(i, list) for p in i]
        return {
            "stmt": "lib",
            "id": str(items[0]),
            "size": _size(items[1]),
            "opts": opts,
            "attrs": attrs,
            "ports": ports,
        }

    def port(self, items: list[Any]) -> tuple:
        pos = str(items[3])
        _, attrs = _opts(items[4:])
        return (
            "port",
            str(items[0]),
            str(items[1]),
            str(items[2]),
            pos[0],
            int(pos[1:]),
            attrs,
        )

    def module(self, items: list[Any]) -> dict:
        body = [d for i in items[1:] if isinstance(i, list) for d in i]
        return {"stmt": "module", "id": str(items[0]), "items": body}

    def module_port(self, items: list[Any]) -> dict:
        cell, pin = str(items[3]).split(".", 1)
        return {
            "stmt": "module_port",
            "id": str(items[0]),
            "direction": str(items[1]),
            "carrier": str(items[2]),
            "cell": cell,
            "pin": pin,
        }

    def macro(self, items: list[Any]) -> dict:
        body = [d for i in items[2:] if isinstance(i, list) for d in i]
        return {
            "stmt": "macro",
            "id": str(items[0]),
            "module": str(items[1]),
            "items": body,
        }

    def lib_items(self, items: list[Any]) -> list:
        return [i for i in items if isinstance(i, tuple) and i[0] == "port"]

    def module_items(self, items: list[Any]) -> list:
        return [i for i in items if isinstance(i, dict)]

    def macro_items(self, items: list[Any]) -> list:
        return [i for i in items if isinstance(i, dict)]

    def opt(self, items: list[Any]) -> tuple:
        key = str(items[0])[:-1]
        raw = items[1]
        value = (
            unquote(str(raw))
            if raw.type == "STRING"
            else parse_value(str(raw), rates=False)
        )
        return ("opt", key, value)

    def attr(self, items: list[Any]) -> tuple:
        key = str(items[0])[1:-1]
        raw = items[1]
        value = (
            unquote(str(raw))
            if raw.type == "STRING"
            else parse_value(str(raw), rates=False)
        )
        return ("attr", key, value)

    def PINREF(self, token: lark.Token) -> lark.Token:
        return token

    def __default__(self, data: Any, children: list[Any], meta: Any) -> Any:
        return children[0] if len(children) == 1 else children
