"""cli: verify, json, text, pretty, flatten and diff over the fixtures, through typer's runner."""

import json
from pathlib import Path

from typer.testing import CliRunner

from kohakulayout.cli import app

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
TWO = str(FIXTURES / "two_gates.kl")
HIER = str(FIXTURES / "half_adder_hier.kl")
runner = CliRunner()


def test_verify_reports_every_level_and_fails_on_a_broken_file(tmp_path: Path) -> None:
    result = runner.invoke(app, ["verify", TWO, HIER, str(FIXTURES / "assessment.kl")])
    assert result.exit_code == 0, result.output
    assert (
        "problem: ok" in result.output
        and "layout: ok" in result.output
        and "assessment: ok" in result.output
    )
    broken = tmp_path / "broken.kl"
    broken.write_text("kl 1\ncell a\n", encoding="utf-8")
    result = runner.invoke(app, ["verify", str(broken)])
    assert result.exit_code == 1 and "line 2" in result.output


def test_json_text_and_flatten_round_trip(tmp_path: Path) -> None:
    out = tmp_path / "two.json"
    assert (
        runner.invoke(
            app, ["json", TWO, "--level", "problem", "-o", str(out)]
        ).exit_code
        == 0
    )
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["level"] == "problem" and data["physics"] == "gates@1"
    text = runner.invoke(app, ["text", str(out)])
    assert text.exit_code == 0 and "cell g1 AND" in text.output
    flat = runner.invoke(app, ["flatten", HIER, "--level", "netlist"])
    assert (
        flat.exit_code == 0
        and "cell h0/x1 XOR" in flat.output
        and "module" not in flat.output
    )
    lay = runner.invoke(app, ["flatten", HIER, "--level", "layout"])
    assert lay.exit_code == 0 and "place h1/x2 4,4 r90" in lay.output


def test_pretty_and_diff(tmp_path: Path) -> None:
    picture = runner.invoke(app, ["pretty", TWO, "--level", "layout"])
    assert (
        picture.exit_code == 0
        and "layer ground" in picture.output
        and "AAA" in picture.output
    )
    same = runner.invoke(app, ["diff", TWO, TWO])
    assert same.exit_code == 1 or "identical" in same.output
    a = tmp_path / "a.kl"
    a.write_text("kl 1\nlib G 1x1 { y out wire E0 }\ncell a G\n", encoding="utf-8")
    b = tmp_path / "b.kl"
    b.write_text(
        "kl 1\nlib G 1x1 { y out wire E0 }\ncell a G kind=nand\n", encoding="utf-8"
    )
    different = runner.invoke(app, ["diff", str(a), str(b)])
    assert different.exit_code == 1 and "cells" in different.output
