from __future__ import annotations

from pathlib import Path
import unittest

from runtime.ui.telegram.details import HOME_CALLBACK_DATA
from telegram_panel import _TERMINAL_CALLBACKS, _is_workspace_callback


ROOT = Path(__file__).resolve().parents[1]


class V3NavigationUICutoverTests(unittest.TestCase):
    def test_canonical_home_callback_is_terminal(self):
        self.assertEqual(HOME_CALLBACK_DATA, "ui:nav.home")
        self.assertIn(HOME_CALLBACK_DATA, _TERMINAL_CALLBACKS)
        self.assertFalse(_is_workspace_callback(HOME_CALLBACK_DATA))

    def test_raw_back_callbacks_and_handlers_are_retired(self):
        runtime_source = (ROOT / "runtime" / "v2_runtime.py").read_text(encoding="utf-8")
        self.assertNotIn('F.data == "dash_back"', runtime_source)
        self.assertNotIn('F.data == "charge_back"', runtime_source)
        self.assertNotIn("async def dashboard_back_handler(", runtime_source)
        self.assertNotIn("async def charge_back_handler(", runtime_source)

        for rel in (
            "runtime/v2_runtime.py",
            "v2_ui_polish.py",
            "v2_bootstrap.py",
            "v2_bot_ui.py",
        ):
            source = (ROOT / rel).read_text(encoding="utf-8")
            self.assertNotIn('callback_data="dash_back"', source, rel)
            self.assertNotIn('callback_data="charge_back"', source, rel)
            self.assertIn("HOME_CALLBACK_DATA", source, rel)

        self.assertFalse(_is_workspace_callback("dash_back"))
        self.assertFalse(_is_workspace_callback("charge_back"))


if __name__ == "__main__":
    unittest.main()
