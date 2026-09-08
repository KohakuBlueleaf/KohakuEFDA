"""Import-order lint for ``src/kohakulayout``: tiers, cycles, in-function imports, isolation.

    python scripts/dev/kl_deps.py            # report, exit 1 on any violation
    python scripts/dev/kl_deps.py --json     # the same as JSON

The framework's subpackages import one way, from ``errors`` up to ``cli``; a module may
import its own tier or a lower one. ``utils`` imports only ``ir`` and ``errors``. Nothing in
``kohakulayout`` imports ``kohakuefda``, and nothing in ``kohakuefda`` imports
``kohakulayout`` until milestone 13. In-function imports need a try/except ImportError
guard or an entry in ``scripts/dev/kl_deps_allowlist.json`` with a reason.
"""

import argparse
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRAMEWORK = ROOT / "src" / "kohakulayout"
PROJECT = ROOT / "src" / "kohakuefda"
PKG = "kohakulayout"
ALLOWLIST = ROOT / "scripts" / "dev" / "kl_deps_allowlist.json"

TIERS = {
    "errors": 0,
    "_rust": 1,
    "_rust_bridge": 1,
    "ir": 1,
    "utils": 2,
    "physics": 3,
    "state": 4,
    "flow": 5,
    "verify": 6,
    "engine": 7,
    "solvers": 8,
    "pipeline": 9,
    "service": 10,
    "templates": 11,
    "cli": 12,
}
TOP_TIER = 13
UTILS_MAY_IMPORT = {"errors", "ir", "_rust", "_rust_bridge", "utils"}
GUARDS = {"ImportError", "ModuleNotFoundError"}


def module_name(path: Path, root: Path) -> str:
    parts = list(path.relative_to(root.parent).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def tier_of(module: str) -> int:
    parts = module.split(".")
    if len(parts) == 1:
        return TOP_TIER
    return TIERS.get(parts[1], TOP_TIER)


def imports_of(tree: ast.AST) -> list[tuple[str, int, bool, bool]]:
    """(target, lineno, in_function, guarded) for every import in the tree."""
    guarded_nodes: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Try) and any(
            getattr(h.type, "id", None) in GUARDS for h in node.handlers
        ):
            guarded_nodes.update(id(n) for n in ast.walk(node))
    function_nodes: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            function_nodes.update(id(n) for n in ast.walk(node))
    typing_only: set[int] = set()
    for node in ast.walk(tree):
        test = node.test if isinstance(node, ast.If) else None
        if (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
            isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
        ):
            typing_only.update(id(n) for n in ast.walk(node))
    out = []
    for node in ast.walk(tree):
        if id(node) in typing_only:
            continue
        targets: list[str] = []
        if isinstance(node, ast.Import):
            targets = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            targets = [node.module]
        for target in targets:
            out.append(
                (
                    target,
                    node.lineno,
                    id(node) in function_nodes,
                    id(node) in guarded_nodes,
                )
            )
    return out


def load_allowlist() -> list[dict]:
    if not ALLOWLIST.exists():
        return []
    return json.loads(ALLOWLIST.read_text(encoding="utf-8"))


def allowed(
    entry_file: str, lineno: int, target: str, tree: ast.AST, allowlist: list[dict]
) -> bool:
    function = ""
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and (
            node.lineno <= lineno <= (node.end_lineno or node.lineno)
        ):
            function = node.name
    return any(
        e.get("file") == entry_file
        and e.get("function") == function
        and e.get("target") == target
        and e.get("reason")
        for e in allowlist
    )


def check_framework() -> tuple[list[str], dict[str, set[str]]]:
    violations: list[str] = []
    graph: dict[str, set[str]] = {}
    allowlist = load_allowlist()
    for path in sorted(FRAMEWORK.rglob("*.py")):
        rel = str(path.relative_to(ROOT))
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        module = module_name(path, FRAMEWORK)
        graph.setdefault(module, set())
        own = tier_of(module)
        for target, lineno, in_function, guarded in imports_of(tree):
            top = target.split(".")[0]
            if top == "kohakuefda":
                violations.append(
                    f"{rel}:{lineno}: framework imports a project: {target}"
                )
                continue
            if (
                in_function
                and not guarded
                and not allowed(rel, lineno, target, tree, allowlist)
            ):
                violations.append(
                    f"{rel}:{lineno}: import inside a function without an allowlist reason: {target}"
                )
            if top != PKG:
                continue
            graph[module].add(target)
            if module.split(".")[1:2] == ["utils"] and len(target.split(".")) > 1:
                if target.split(".")[1] not in UTILS_MAY_IMPORT:
                    violations.append(
                        f"{rel}:{lineno}: utils may import only ir: {target}"
                    )
                continue
            if tier_of(target) > own:
                violations.append(
                    f"{rel}:{lineno}: {module} (tier {own}) imports {target} (tier {tier_of(target)})"
                )
    return violations, graph


def check_project() -> list[str]:
    violations: list[str] = []
    if not PROJECT.exists():
        return violations
    for path in sorted(PROJECT.rglob("*.py")):
        rel = str(path.relative_to(ROOT))
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        for target, lineno, _, _ in imports_of(tree):
            if target.split(".")[0] == PKG:
                violations.append(
                    f"{rel}:{lineno}: project imports the framework before milestone 13: {target}"
                )
    return violations


def _resolve(target: str, graph: dict[str, set[str]]) -> str | None:
    if target in graph:
        return target
    parts = target.split(".")
    while len(parts) > 1:
        parts = parts[:-1]
        candidate = ".".join(parts)
        if candidate in graph:
            return candidate
    return None


def cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    """Strongly connected components of size above one, by Tarjan's algorithm."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    out: list[list[str]] = []
    counter = [0]

    def visit(node: str) -> None:
        index[node] = low[node] = counter[0]
        counter[0] += 1
        stack.append(node)
        on_stack.add(node)
        for succ in graph.get(node, ()):
            resolved = _resolve(succ, graph)
            if resolved is None or resolved == node:
                continue
            if resolved not in index:
                visit(resolved)
                low[node] = min(low[node], low[resolved])
            elif resolved in on_stack:
                low[node] = min(low[node], index[resolved])
        if low[node] == index[node]:
            component = []
            while True:
                item = stack.pop()
                on_stack.discard(item)
                component.append(item)
                if item == node:
                    break
            if len(component) > 1:
                out.append(sorted(component))

    for node in sorted(graph):
        if node not in index:
            visit(node)
    return out


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    violations, graph = check_framework()
    violations += check_project()
    violations += [f"import cycle: {' -> '.join(c)}" for c in cycles(graph)]
    if args.json:
        print(json.dumps({"violations": violations, "modules": len(graph)}, indent=2))
    else:
        for line in violations:
            print(line)
        print(f"kl_deps: {len(graph)} modules, {len(violations)} violation(s)")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
