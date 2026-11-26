"""Dependency-free source contract for app-scoped ownership HMI composition."""
import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def _function_source(path: str, name: str) -> str:
    source = (ROOT / path).read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(
        item for item in tree.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == name
    )
    return ast.get_source_segment(source, node) or ""


class OwnershipHmiCompositionContractTests(unittest.TestCase):
    def test_recovery_installer_registers_callbacks_without_global_keyboard_assignment(self):
        source = _function_source("rd_ownership_recovery.py", "install_rd_ownership_recovery")
        self.assertNotIn("hmi.build_operator_keyboard =", source)
        self.assertIn("app._rd_ownership_recovery_installed = True", source)
        self.assertIn('F.data == "rd_ownership_hands_off"', source)
        self.assertIn('F.data == "rd_ownership_adopt"', source)
        self.assertIn('F.data == "rd_ownership_output_off"', source)

    def test_projection_uses_only_current_app_owners_and_existing_renderer(self):
        source = _function_source(
            "runtime/ui/components/hmi_action_keyboard.py",
            "_ownership_recovery_keyboard",
        )
        self.assertIn('getattr(app, "_rd_ownership_recovery_installed", False)', source)
        self.assertIn('getattr(app, "rd_control_mode_manager", None)', source)
        self.assertIn('getattr(app, "rd_managed_live_adoption", None)', source)
        component = (ROOT / "runtime/ui/components/hmi_action_keyboard.py").read_text(encoding="utf-8")
        self.assertNotIn("InlineKeyboardButton", component)
        self.assertIn("from runtime.ui.telegram.renderer import", component)

    def test_operator_hmi_composes_projection_before_final_safety_filter(self):
        source = _function_source("operator_hmi.py", "build_operator_keyboard")
        project = source.index("_ownership_recovery_keyboard(app, state, markup, actions=actions)")
        safety = source.index("filter_keyboard_for_output_truth(app, state, markup, hmi)")
        self.assertLess(project, safety)

    def test_managed_stop_installer_keeps_handlers_without_global_keyboard_patch(self):
        source = _function_source("operator_managed_stop.py", "install_operator_managed_stop")
        self.assertNotIn("hmi.build_operator_keyboard =", source)
        self.assertIn("app._operator_managed_stop_installed = True", source)
        for callback in ("STOP_CONFIRM_CALLBACK", "STOP_EXECUTE_CALLBACK", "STOP_CANCEL_CALLBACK"):
            self.assertIn(callback, source)

    def test_managed_stop_is_app_projected_before_final_output_filter(self):
        source = _function_source("operator_hmi.py", "build_operator_keyboard")
        project = source.index("_managed_stop_keyboard(app, state, markup, actions=actions)")
        safety = source.index("filter_keyboard_for_output_truth(app, state, markup, hmi)")
        self.assertLess(project, safety)
        component = _function_source(
            "runtime/ui/components/hmi_action_keyboard.py", "_managed_stop_keyboard"
        )
        self.assertIn('getattr(app, "_operator_managed_stop_installed", False)', component)
        self.assertIn("_active_session_token(app)", component)
        self.assertIn("_orphan_stop_token(app)", component)


if __name__ == "__main__":
    unittest.main()
