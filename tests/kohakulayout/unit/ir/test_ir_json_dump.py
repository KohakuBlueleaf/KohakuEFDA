"""ir/json.py and ir/dump.py: dispatch on the level key, and the picture."""

from pathlib import Path

import pytest

from kohakulayout.errors import IRError
from kohakulayout.ir import Assessment, parse_text
from kohakulayout.ir.dump import dump
from kohakulayout.ir.json import dumps, loads, pretty

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def test_loads_dispatches_and_rejects() -> None:
    assessment = parse_text(
        (FIXTURES / "assessment.kl").read_text(encoding="utf-8")
    ).assessment
    assert isinstance(loads(dumps(assessment)), Assessment)
    assert '"level": "assessment"' in pretty(assessment)
    with pytest.raises(IRError):
        loads('{"level": "nope"}')
    with pytest.raises(IRError):
        loads("[]")
    with pytest.raises(IRError):
        loads("{not json")


def test_dump_draws_footprints_and_wires() -> None:
    levels = parse_text((FIXTURES / "two_gates.kl").read_text(encoding="utf-8"))
    picture = dump(levels.layout, levels.netlist, levels.fabric)
    assert "layer ground" in picture and "layer overhead" in picture
    ground = picture.split("layer overhead")[0]
    assert ground.count("A") == 9 and "I" in ground and "O" in ground
    assert "─" in ground and "╴" in ground
    alone = dump(levels.layout)
    assert "#" in alone
