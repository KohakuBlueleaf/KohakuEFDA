"""Comment-budget checker: inline comment runs at most 2 lines, docstrings at most 14 lines.

Usage: ``python scripts/dev/comment_budget.py src scripts tests``. A line ``# justify: <reason>``
directly above an item exempts that item. Module docstrings are exempt. Exit status 1 on any
violation.
"""

import ast
import sys
import tokenize
from pathlib import Path

MAX_INLINE_LINES = 2
MAX_DOCSTRING_LINES = 14
JUSTIFY = "# justify:"
SKIP_PREFIXES = ("#!", "# -*-", "# noqa", "# type:", "# fmt:", "# pragma:", JUSTIFY)
EXCLUDED_DIRS = {
    "node_modules",
    ".venv",
    "web_dist",
    "__pycache__",
    ".ref",
    ".internal",
}


def _comment_runs(path: Path) -> list[tuple[int, int]]:
    """Return (start_line, length) of every run of consecutive full-line comments."""
    runs: list[tuple[int, int]] = []
    start = 0
    length = 0
    last_line = 0
    with tokenize.open(path) as handle:
        for tok in tokenize.generate_tokens(handle.readline):
            if tok.type != tokenize.COMMENT:
                continue
            is_full_line = tok.line.strip().startswith("#")
            if not is_full_line or tok.string.startswith(SKIP_PREFIXES):
                if length:
                    runs.append((start, length))
                start = length = 0
                continue
            if length and tok.start[0] == last_line + 1:
                length += 1
            else:
                if length:
                    runs.append((start, length))
                start, length = tok.start[0], 1
            last_line = tok.start[0]
    if length:
        runs.append((start, length))
    return runs


def _justified(lines: list[str], lineno: int) -> bool:
    """True when the line above ``lineno`` (1-based) is a ``# justify:`` line."""
    return lineno >= 2 and lines[lineno - 2].strip().startswith(JUSTIFY)


def _docstring_violations(path: Path, lines: list[str]) -> list[str]:
    tree = ast.parse("".join(lines), filename=str(path))
    out: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            continue
        doc = ast.get_docstring(node, clean=False)
        if doc is None:
            continue
        n_lines = doc.count("\n") + 1
        if n_lines > MAX_DOCSTRING_LINES and not _justified(lines, node.lineno):
            out.append(
                f"{path}:{node.lineno}: docstring of {node.name} is {n_lines} lines"
            )
    return out


def check_file(path: Path) -> list[str]:
    """Return every budget violation in ``path`` as ``file:line: message``."""
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    out = [
        f"{path}:{start}: inline comment run is {length} lines"
        for start, length in _comment_runs(path)
        if length > MAX_INLINE_LINES and not _justified(lines, start)
    ]
    return out + _docstring_violations(path, lines)


def main(argv: list[str]) -> int:
    roots = [Path(arg) for arg in argv] or [Path("src")]
    violations: list[str] = []
    for root in roots:
        for path in sorted(root.rglob("*.py")):
            if EXCLUDED_DIRS.intersection(path.parts):
                continue
            violations.extend(check_file(path))
    for line in violations:
        print(line)
    print(f"comment budget: {len(violations)} violation(s)")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
