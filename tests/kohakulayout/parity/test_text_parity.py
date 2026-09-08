"""Every .kl fixture through both sides: the same levels JSON, the same text, the same digest, the same flat form."""

import glob
import json
import os
from importlib.resources import files
from pathlib import Path

import pytest

from kohakulayout.ir import parse_text, write

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = sorted(
    glob.glob(str(ROOT / "tests" / "kohakulayout" / "fixtures" / "*.kl"))
) + sorted(
    str(p)
    for p in files("kohakulayout.templates.physics.gates")
    .joinpath("fixtures")
    .iterdir()
    if str(p).endswith(".kl")
)


@pytest.fixture(autouse=True)
def python_side(monkeypatch: pytest.MonkeyPatch):
    """The Python reference must produce the expectation; the twin is called directly."""
    import kohakulayout._rust_bridge as bridge

    monkeypatch.setattr(bridge, "BACKEND", "python")
    yield


@pytest.mark.parametrize("path", FIXTURES, ids=[Path(p).name for p in FIXTURES])
def test_fixture_agrees_on_both_sides(path: str) -> None:
    import kohakulayout_rs as rs

    text = Path(path).read_text()
    python = parse_text(text)
    native = json.loads(rs.parse_kl(text))
    for name in ("problem", "netlist", "layout", "assessment"):
        level = getattr(python, name)
        assert (level is None) == (native.get(name) is None), name
        if level is None:
            continue
        assert json.loads(level.to_json()) == native[name], f"{name}: levels JSON"
        assert level.digest() == rs.digest(level.to_json()), f"{name}: digest"
        context = python.problem if name == "layout" else None
        assert write(level, context) == rs.write_kl(
            level.to_json(), context.to_json() if context else None
        ), f"{name}: text"
        if name in ("netlist", "problem"):
            flat = (
                level.model_copy(update={"netlist": level.netlist.flatten()})
                if name == "problem"
                else level.flatten()
            )
            assert json.loads(flat.to_json()) == json.loads(
                rs.flatten(level.to_json())
            ), f"{name}: flatten"


def test_backend_variable_forces_a_side(monkeypatch: pytest.MonkeyPatch) -> None:
    import kohakulayout._rust_bridge as bridge

    monkeypatch.setattr(bridge, "BACKEND", "native")
    text = Path(FIXTURES[0]).read_text()
    assert bridge.rust_parse_kl(text) is not None
    monkeypatch.setattr(bridge, "BACKEND", "python")
    assert bridge.rust_parse_kl(text) is None
    assert os.environ.get("KOHAKULAYOUT_BACKEND", "auto") in (
        "auto",
        "python",
        "native",
    )
