#!/usr/bin/env python3
"""PostToolUse hook: the file rules of the KohakuLayout tree, advisory after every edit.

Runs on a Python file under src/kohakulayout, tests/kohakulayout or scripts/dev/kl_*: the
comment budget, the 600-line cap, in-function imports and any import of a project package.
It only advises: exit 0, findings returned as additional context.
"""

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "dev"))

SOFT_LINES = 600
HARD_LINES = 1000
PROJECT_PREFIXES = ("kohakuefda",)
GUARDED_EXCEPTIONS = {"ImportError", "ModuleNotFoundError"}


def _in_scope(path: Path) -> bool:
    try:
        rel = path.resolve().relative_to(ROOT)
    except ValueError:
        return False
    parts = rel.parts
    if rel.suffix != ".py":
        return False
    return (
        parts[:2] == ("src", "kohakulayout")
        or parts[:2] == ("tests", "kohakulayout")
        or (parts[:2] == ("scripts", "dev") and rel.name.startswith("kl_"))
    )


def _guarded(node: ast.AST, tree: ast.AST) -> bool:
    for parent in ast.walk(tree):
        if isinstance(parent, ast.Try):
            names = {getattr(h.type, "id", None) for h in parent.handlers}
            if names & GUARDED_EXCEPTIONS and any(n is node for n in ast.walk(parent)):
                return True
    return False


def in_function_imports(tree: ast.AST) -> list[int]:
    lines: list[int] = []
    for func in ast.walk(tree):
        if not isinstance(func, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for node in ast.walk(func):
            if isinstance(node, ast.Import | ast.ImportFrom) and not _guarded(
                node, tree
            ):
                lines.append(node.lineno)
    return sorted(set(lines))


def project_imports(tree: ast.AST, path: Path) -> list[str]:
    if "kohakulayout" not in path.parts:
        return []
    out: list[str] = []
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        for name in names:
            if name.split(".")[0] in PROJECT_PREFIXES:
                out.append(f"{path}:{node.lineno}: framework imports a project: {name}")
    return out


def check(path: Path) -> list[str]:
    from comment_budget import check_file

    findings = list(check_file(path))
    source = path.read_text(encoding="utf-8")
    n_lines = source.count("\n") + 1
    if n_lines > HARD_LINES:
        findings.append(f"{path}: {n_lines} lines, over the hard cap of {HARD_LINES}")
    elif n_lines > SOFT_LINES:
        findings.append(
            f"{path}: {n_lines} lines, over the soft cap of {SOFT_LINES}; split it"
        )
    tree = ast.parse(source, filename=str(path))
    for lineno in in_function_imports(tree):
        findings.append(f"{path}:{lineno}: import inside a function")
    findings.extend(project_imports(tree, path))
    return findings


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path") or (payload.get("tool_response") or {}).get(
        "filePath"
    )
    if not file_path:
        return 0
    path = Path(file_path)
    if not _in_scope(path) or not path.is_file():
        return 0
    try:
        findings = check(path)
    except SyntaxError as exc:
        findings = [f"{path}: does not parse: {exc}"]
    if not findings:
        return 0
    context = "KohakuLayout file rules (advisory):\n" + "\n".join(findings)
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": context,
                }
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
