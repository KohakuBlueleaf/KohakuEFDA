"""``kl solve`` and ``kl assess``."""

from pathlib import Path

from typer.testing import CliRunner

from kohakulayout.cli import app
from kohakulayout.cli.io import load_all
from kohakulayout.ir import write
from kohakulayout.templates.physics.gates import from_expressions, problem


def test_solve_then_assess(tmp_path: Path) -> None:
    prob = problem(from_expressions("y = a & b | ~c"), width=24, height=12)
    problem_path, out_path = tmp_path / "p.kl", tmp_path / "l.kl"
    problem_path.write_text(prob.text())
    result = CliRunner().invoke(
        app,
        [
            "solve",
            str(problem_path),
            "--out",
            str(out_path),
            "--units",
            "800",
            "-p",
            "tries=32",
        ],
    )
    assert result.exit_code == 0, result.output
    layout = load_all([problem_path, out_path]).layout
    assert set(layout.wires) == set(prob.netlist.nets)
    assessed = CliRunner().invoke(app, ["assess", str(problem_path), str(out_path)])
    assert assessed.exit_code == 0, assessed.output
    assert "valid" in assessed.output
    bare = tmp_path / "bare.kl"
    bare.write_text(write(layout.model_copy(update={"wires": {}, "units": {}}), prob))
    assert (
        CliRunner().invoke(app, ["assess", str(problem_path), str(bare)]).exit_code == 1
    )
    assert (
        CliRunner()
        .invoke(app, ["solve", str(problem_path), "--solver", "nowhere"])
        .exit_code
        == 1
    )
