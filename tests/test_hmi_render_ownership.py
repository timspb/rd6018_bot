"""Single read-only panel and keyboard renderer across compatibility imports."""
import unittest
from application.operator_actions import OperatorAction, OperatorActionSpec, OperatorActionsView
from runtime.ui.components.hmi_action_keyboard import _keyboard_from_actions
from runtime.ui.components.hmi_panel_text import render_operator_panel
import operator_hmi

class HmiRenderingOwnershipTests(unittest.TestCase):
    def test_panel_renderer_exists_and_legacy_source_reexports_it(self):
        # Integration tests may install an existing runtime wrapper; verify
        # the import boundary without assuming function identity afterward.
        from runtime.ui.components.hmi_state import HmiAuthority, HmiProcessState, OperatorHmiState
        import ast
        from pathlib import Path
        source = Path(operator_hmi.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        self.assertFalse(any(
            isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            and item.name == "render_operator_panel" for item in tree.body
        ))
        self.assertTrue(any(
            isinstance(item, ast.ImportFrom)
            and item.module == "runtime.ui.components.hmi_panel_text"
            and any(alias.name == "render_operator_panel" for alias in item.names)
            for item in tree.body
        ))
        state = OperatorHmiState(
            HmiProcessState.IDLE, HmiAuthority.NONE, "RD6018 test", False,
            "-", "", None, None, None, None, None, None, None, "", "safe",
        )
        output = render_operator_panel(state)
        self.assertIn("RD6018 test", output)
        self.assertTrue(callable(operator_hmi.render_operator_panel))

    def test_legacy_api_is_same_action_keyboard_renderer(self):
        self.assertIs(operator_hmi._keyboard_from_actions, _keyboard_from_actions)
        actions=OperatorActionsView((OperatorActionSpec(OperatorAction.REAUTHORIZE_MANUAL),
                                     OperatorActionSpec(OperatorAction.DISCARD_MANUAL)))
        keyboard=operator_hmi._keyboard_from_actions(actions)
        rows=[[button.callback_data for button in row] for row in keyboard.inline_keyboard]
        self.assertEqual(rows[0],["v2_manual_reauthorize","v2_manual_discard"])
        self.assertEqual(rows[-1],["operator_refresh"])
