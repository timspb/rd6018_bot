from pathlib import Path
import ast
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ProductionModuleNamespaceTests(unittest.TestCase):
    def test_no_production_python_filename_uses_v2_namespace(self):
        offenders = []
        for path in ROOT.rglob("*.py"):
            if any(part in {".git", "__pycache__", "tests"} for part in path.parts):
                continue
            if "v2" in path.name.lower():
                offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual([], offenders)

    def test_retired_module_imports_are_absent_from_production_sources(self):
        retired = {
            "auto_strategy_v2", "charge_controller_v2", "manual_context_v2",
            "manual_runtime_v2", "manual_text_v2", "runtime_safety_v2",
            "sg_policy_v2", "v2_authority", "v2_battery_catalog",
            "v2_battery_input", "v2_bootstrap", "v2_bot_ui", "v2_mix_mode",
            "v2_sg_ui", "v2_ui", "v2_ui_polish", "runtime.v2_startup_recovery",
            "application.v2_v3_comparison",
        }
        violations = []
        for path in ROOT.rglob("*.py"):
            if any(part in {".git", "__pycache__", "tests"} for part in path.parts):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                for name in names:
                    if name in retired:
                        violations.append(f"{path.relative_to(ROOT)}:{name}")
        self.assertEqual([], violations)

    def test_canonical_module_names_exist(self):
        for rel in (
            "auto_strategy.py", "charge_controller.py", "manual_context.py",
            "manual_runtime.py", "manual_text.py", "managed_runtime_safety.py",
            "sg_policy.py", "charge_authority.py", "battery_catalog.py",
            "battery_input.py", "production_bootstrap.py", "production_bot_ui.py",
            "mix_mode.py", "sg_ui.py", "ui_support.py", "ui_polish.py",
            "runtime/startup_recovery.py", "application/decision_comparison.py",
        ):
            self.assertTrue((ROOT / rel).is_file(), rel)


if __name__ == "__main__":
    unittest.main()
