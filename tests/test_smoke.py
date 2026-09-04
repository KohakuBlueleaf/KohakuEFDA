"""Package import and CLI entry smoke tests."""

from typer.testing import CliRunner

import kohakuefda
from kohakuefda.cli.__main__ import app


def test_version_string() -> None:
    assert kohakuefda.__version__.count(".") == 2


def test_cli_version_flag() -> None:
    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert kohakuefda.__version__ in result.output


def test_cli_lists_every_command() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in (
        "data",
        "plan",
        "netlist",
        "cell",
        "layout",
        "check",
        "render",
        "view",
    ):
        assert command in result.output
