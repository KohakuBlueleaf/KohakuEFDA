"""CLI commands that read the shipped dataset."""

from pathlib import Path

from typer.testing import CliRunner

from kohakuefda.cli.__main__ import app

ROOT = Path(__file__).resolve().parents[1] / "data"


def test_data_show_machines_in_traditional_chinese() -> None:
    result = CliRunner().invoke(
        app, ["data", "show", "machines", "--root", str(ROOT), "--lang", "zh-TW"]
    )
    assert result.exit_code == 0, result.output
    assert "精煉爐" in result.output


def test_glossary_lists_items() -> None:
    result = CliRunner().invoke(app, ["glossary", "items", "--root", str(ROOT)])
    assert result.exit_code == 0, result.output
    assert "Clean Water" in result.output


def test_data_show_rejects_unknown_collection() -> None:
    result = CliRunner().invoke(app, ["data", "show", "nope", "--root", str(ROOT)])
    assert result.exit_code != 0
