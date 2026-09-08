"""Reading and writing levels from files: ``.kl`` through the text form, ``.json`` through the canonical JSON."""

from pathlib import Path

from kohakulayout.errors import IRError
from kohakulayout.ir import (
    Assessment,
    Layout,
    Level,
    Levels,
    Netlist,
    Problem,
    parse_text,
)
from kohakulayout.ir.json import loads


def levels_from_file(path: Path, context: Levels | None = None) -> Levels:
    """Every level a file holds. JSON files hold exactly one; ``.kl`` files may hold several."""
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        level = loads(text)
        out = Levels(
            physics=context.physics if context else "",
            fabric=context.fabric if context else None,
            netlist=context.netlist if context else None,
        )
        if isinstance(level, Problem):
            out.physics, out.fabric, out.netlist, out.params = (
                level.physics,
                level.fabric,
                level.netlist,
                level.params,
            )
        elif isinstance(level, Netlist):
            out.netlist = level
        elif isinstance(level, Layout):
            out.layout = level
        elif isinstance(level, Assessment):
            out.assessment = level
        else:
            raise IRError(f"{path}: no file form for {level.level}")
        return out
    return parse_text(text, context)


def merge(into: Levels, more: Levels) -> Levels:
    """Later files win field by field; a problem's parts come along together."""
    if more.physics:
        into.physics = more.physics
    if more.params:
        into.params = {**into.params, **more.params}
    for name in ("fabric", "netlist", "layout", "assessment"):
        value = getattr(more, name)
        if value is not None:
            setattr(into, name, value)
    return into


def load_all(paths: list[Path]) -> Levels:
    out = Levels()
    for path in paths:
        out = merge(out, levels_from_file(path, out))
    return out


def present(levels: Levels) -> list[Level]:
    found: list[Level] = []
    if levels.problem is not None:
        found.append(levels.problem)
    elif levels.netlist is not None:
        found.append(levels.netlist)
    if levels.layout is not None:
        found.append(levels.layout)
    if levels.assessment is not None:
        found.append(levels.assessment)
    return found


def pick(levels: Levels, name: str | None) -> Level:
    """The level named by ``name`` (problem, netlist, layout, assessment) or the only one present."""
    if name is None:
        found = present(levels)
        if len(found) != 1:
            names = [level.level for level in found]
            raise IRError(
                f"the file holds {names or 'no level'}; say which with --level"
            )
        return found[0]
    level = {
        "problem": levels.problem,
        "netlist": levels.netlist,
        "layout": levels.layout,
        "assessment": levels.assessment,
    }.get(name)
    if level is None:
        raise IRError(f"no {name} in the given files")
    return level


def write_out(text: str, out: Path | None) -> None:
    if out is None:
        print(text, end="" if text.endswith("\n") else "\n")
    else:
        out.write_text(text, encoding="utf-8")
