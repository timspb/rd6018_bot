import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
UI_PROVIDER = ROOT / "application" / "operator_snapshot_provider.py"


class ApplicationRuntimeGuardrailTests(unittest.TestCase):
    def test_operator_snapshot_provider_has_no_historical_runtime_or_transport_imports(self):
        tree = ast.parse(UI_PROVIDER.read_text(encoding="utf-8"), filename=str(UI_PROVIDER))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")
        for retired in (
            "operator_hmi", "rd6018_telemetry", "legacy_ui_boundary",
            "runtime.v2_runtime", "application.operator_interface",
        ):
            self.assertNotIn(retired, imports)
        self.assertIn("operator_read_source", imports)

    def test_application_modules_do_not_start_runtime_implicitly(self):
        for path in (ROOT / "application").rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imports.append(node.module or "")
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    self.assertNotEqual(
                        (getattr(node.func.value, "id", ""), node.func.attr),
                        ("asyncio", "run"),
                        path.name,
                    )
            self.assertNotIn("runtime.v2_runtime", imports, path.name)


if __name__ == "__main__":
    unittest.main()
