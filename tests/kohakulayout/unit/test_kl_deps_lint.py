"""Guard the import-order lint: the framework tree passes it, and the lint catches a cycle."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "dev" / "kl_deps.py"


def _load():
    spec = importlib.util.spec_from_file_location("kl_deps", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_framework_passes_the_lint() -> None:
    kl_deps = _load()
    violations, graph = kl_deps.check_framework()
    violations += kl_deps.check_project()
    assert graph, "no framework modules were scanned"
    assert violations == [], "\n".join(violations)
    assert kl_deps.cycles(graph) == []


def test_tiers_order_and_cycles() -> None:
    kl_deps = _load()
    assert kl_deps.tier_of("kohakulayout.ir.base") < kl_deps.tier_of(
        "kohakulayout.state.world"
    )
    assert kl_deps.tier_of("kohakulayout.cli") > kl_deps.tier_of(
        "kohakulayout.service.local"
    )
    assert kl_deps.cycles({"a": {"b"}, "b": {"a"}, "c": set()}) == [["a", "b"]]
