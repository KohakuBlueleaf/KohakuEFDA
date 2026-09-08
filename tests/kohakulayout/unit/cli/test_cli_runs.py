"""``kl solve --root`` records a run and ``kl runs`` lists it."""

from pathlib import Path

from typer.testing import CliRunner

from kohakulayout.cli import app
from kohakulayout.templates.physics.gates import from_expressions, problem


def test_solve_through_the_service_and_list(tmp_path: Path) -> None:
    prob = problem(from_expressions("y = a & b"), width=16, height=8)
    problem_path = tmp_path / "p.kl"
    problem_path.write_text(prob.text())
    root = tmp_path / "root"
    result = CliRunner().invoke(
        app, ["solve", str(problem_path), "--root", str(root), "--units", "600"]
    )
    assert result.exit_code == 0, result.output
    assert (root / "runs").exists()
    listed = CliRunner().invoke(app, ["runs", str(root)])
    assert (
        listed.exit_code == 0
        and "done" in listed.output
        and "complete" in listed.output
    )
