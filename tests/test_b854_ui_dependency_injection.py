"""Fake/source regression for B854's existing UI composition boundary."""

import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _function(path, name):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return next(node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == name)


class UiDependencyInjectionTests(unittest.TestCase):
    def test_existing_installer_receives_app_scoped_dependencies_without_global_rebinding(self):
        bootstrap = _function(ROOT / "production_bootstrap.py", "install_production")
        ui_assignments = {
            target.attr
            for node in ast.walk(bootstrap)
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == "production_bot_ui"
        }
        self.assertFalse({
            "upsert_battery", "parse_battery_spec", "_safe_answer",
            "_intent_keyboard", "_preview_keyboard",
        } & ui_assignments)

        install_call = next(
            node for node in ast.walk(bootstrap)
            if isinstance(node, ast.Call)
            and ((isinstance(node.func, ast.Attribute) and node.func.attr == "install_ui_support")
                 or (isinstance(node.func, ast.Name) and node.func.id == "install_ui_support"))
        )
        supplied = {keyword.arg: ast.unparse(keyword.value) for keyword in install_call.keywords}
        self.assertEqual(supplied, {
            "battery_upsert": "_upsert_from_ui",
            "battery_spec_parser": "parse_battery_spec",
            "safe_answer": "_safe_answer_operator",
            "intent_keyboard": "_operator_intent_keyboard",
            "preview_keyboard": "_operator_preview_keyboard",
            "pending_intent_state": "_pending_intent",
            "active_evidence_formatter": "format_active_evidence_pretty",
            "start_route": "app._v3_production_start_route",
        })

        installer = _function(ROOT / "production_bot_ui.py", "install_ui_support")
        accepted = {arg.arg for arg in installer.args.kwonlyargs}
        self.assertEqual(accepted & set(supplied), set(supplied))
        names = {node.id for node in ast.walk(installer) if isinstance(node, ast.Name)}
        self.assertTrue({
            "save_battery", "parse_battery", "answer",
            "build_intent_keyboard", "build_preview_keyboard",
            "pending_intents", "format_evidence",
        } <= names)

        installer_source = (ROOT / "production_bot_ui.py").read_text(encoding="utf-8")
        self.assertIn("pending_intent_state if pending_intent_state is not None else _pending_intent", installer_source)
        self.assertIn("pending_intents.pop(user_id, ChargeIntent.RECOVERY)", installer_source)
        self.assertIn("format_evidence(", installer_source)

    def test_bootstrap_uses_canonical_callable_owners(self):
        path = ROOT / "production_bootstrap.py"
        module = ast.parse(path.read_text(encoding="utf-8"))
        bootstrap = _function(path, "install_production")
        module_reads = {
            node.attr for node in ast.walk(bootstrap)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "production_bot_ui"
        }
        self.assertEqual(module_reads, set())
        imports = {
            (node.module, alias.name, alias.asname)
            for node in module.body if isinstance(node, ast.ImportFrom)
            for alias in node.names
        }
        self.assertIn(("production_bot_ui", "install_ui_support", None), imports)
        self.assertIn(("runtime.ui.components.hmi_values", "format_start_feedback", None), imports)
        self.assertIn(("runtime.ui.telegram.charge", "selected_program_for_user", None), imports)


if __name__ == "__main__":
    unittest.main()
