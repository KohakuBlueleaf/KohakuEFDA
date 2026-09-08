"""The framework's central claim as a test that fails when it stops being true.

``kohakulayout`` must not import any project. The probe runs in a subprocess so that a
project already imported by the test process cannot be blamed on the framework.
"""

import importlib
import pkgutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROJECT_PREFIXES = ("kohakuefda",)

_PROBE = f"""
import importlib, pkgutil, sys
import kohakulayout
names = ["kohakulayout"] + [m.name for m in
         pkgutil.walk_packages(kohakulayout.__path__, "kohakulayout.")]
failed = []
for n in names:
    try:
        importlib.import_module(n)
    except Exception as exc:
        failed.append(f"{{n}}: {{exc!r}}")
bad = sorted(m for m in sys.modules
             if any(m == p or m.startswith(p + ".") for p in {PROJECT_PREFIXES!r}))
print(len(names), ",".join(bad), "|", ";".join(failed))
"""


def _framework_modules() -> list[str]:
    import kohakulayout

    return ["kohakulayout"] + [
        m.name for m in pkgutil.walk_packages(kohakulayout.__path__, "kohakulayout.")
    ]


def test_framework_imports_no_project() -> None:
    """Importing every framework module pulls in no project module, and every one imports."""
    done = subprocess.run(
        [sys.executable, "-c", _PROBE],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        check=False,
    )
    assert done.returncode == 0, done.stderr
    head, _, failed = done.stdout.strip().partition("|")
    count, _, leaked = head.strip().partition(" ")
    assert int(count) >= 1, "walk_packages found no framework modules"
    assert not leaked.strip(), f"kohakulayout pulled in project modules: {leaked}"
    assert not failed.strip(), f"framework modules that do not import: {failed}"


def test_every_framework_module_imports() -> None:
    for name in _framework_modules():
        importlib.import_module(name)
