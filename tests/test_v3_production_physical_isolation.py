from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = (
    "runtime.physical",
    "runtime.output.executor",
    "PhysicalExecutionGate",
    "PhysicalBridgeExecutor",
    "HAESPConnector",
    "ESPDirectConnector",
)


def _module_path(module: str) -> Path | None:
    relative = Path(*module.split("."))
    candidate = ROOT / (str(relative) + ".py")
    if candidate.is_file():
        return candidate
    package_init = ROOT / relative / "__init__.py"
    return package_init if package_init.is_file() else None


def _local_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names if _module_path(alias.name))
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if _module_path(node.module):
                result.add(node.module)
    return result


def _production_import_graph() -> set[str]:
    pending = ["bot"]
    seen: set[str] = set()
    while pending:
        module = pending.pop()
        if module in seen:
            continue
        path = _module_path(module)
        if path is None:
            continue
        seen.add(module)
        pending.extend(_local_imports(path) - seen)
    return seen


class ProductionPhysicalIsolationTests(unittest.TestCase):
    def test_production_import_graph_does_not_reach_physical_execution(self):
        graph = _production_import_graph()
        forbidden = sorted(
            name for name in graph if name == "runtime.physical" or name.startswith("runtime.physical.")
        )
        self.assertEqual(forbidden, [], graph)

    def test_production_sources_do_not_import_physical_execution_symbols(self):
        violations: list[str] = []
        source_paths = [ROOT / "bot.py"] + list((ROOT / "application").rglob("*.py"))
        for path in source_paths:
            text = path.read_text(encoding="utf-8")
            for forbidden in FORBIDDEN:
                if forbidden in text and ("import " in text or "from " in text):
                    violations.append(f"{path.relative_to(ROOT)}:{forbidden}")
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
