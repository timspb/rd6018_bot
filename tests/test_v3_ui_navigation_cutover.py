from __future__ import annotations

from pathlib import Path
import unittest

from runtime.ui.telegram.details import HOME_CALLBACK_DATA
from telegram_panel import _ADOPT_CALLBACKS, _TERMINAL_CALLBACKS, _is_workspace_callback


ROOT = Path(__file__).resolve().parents[1]


class V3NavigationUICutoverTests(unittest.TestCase):
    def test_canonical_home_callback_is_terminal(self):
        self.assertEqual(HOME_CALLBACK_DATA, "ui:nav.home")
        self.assertIn(HOME_CALLBACK_DATA, _TERMINAL_CALLBACKS)
        self.assertFalse(_is_workspace_callback(HOME_CALLBACK_DATA))

    def test_raw_back_callbacks_and_handlers_are_retired(self):
        runtime_source = (ROOT / "runtime" / "production_runtime.py").read_text(encoding="utf-8")
        self.assertNotIn('F.data == "dash_back"', runtime_source)
        self.assertNotIn('F.data == "charge_back"', runtime_source)
        self.assertNotIn("async def dashboard_back_handler(", runtime_source)
        self.assertNotIn("async def charge_back_handler(", runtime_source)

        for rel in (
            "runtime/production_runtime.py",
            "ui_polish.py",
            "production_bootstrap.py",
            "production_bot_ui.py",
        ):
            source = (ROOT / rel).read_text(encoding="utf-8")
            self.assertNotIn('callback_data="dash_back"', source, rel)
            self.assertNotIn('callback_data="charge_back"', source, rel)
            self.assertIn("HOME_CALLBACK_DATA", source, rel)

        self.assertFalse(_is_workspace_callback("dash_back"))
        self.assertFalse(_is_workspace_callback("charge_back"))

    def test_raw_chart_callbacks_are_retired(self):
        runtime_source = (ROOT / "runtime" / "production_runtime.py").read_text(encoding="utf-8")
        panel_source = (ROOT / "telegram_panel.py").read_text(encoding="utf-8")
        self.assertNotIn('F.data.startswith("chart_")', runtime_source)
        self.assertNotIn("async def chart_range_handler(", runtime_source)
        self.assertNotIn('data.startswith("chart_")', panel_source)

        for rel in (
            "runtime/production_runtime.py",
            "ui_polish.py",
            "production_bot_ui.py",
            "operator_hmi.py",
            "operator_dashboard.py",
        ):
            source = (ROOT / rel).read_text(encoding="utf-8")
            self.assertNotIn('callback_data="chart_', source, rel)
            self.assertNotIn('callback_data=f"chart_', source, rel)

        operator_hmi = (ROOT / "operator_hmi.py").read_text(encoding="utf-8")
        self.assertIn('F.data.startswith("operator_graph_")', operator_hmi)

    def test_raw_refresh_callback_is_retired(self):
        runtime_source = (ROOT / "runtime" / "production_runtime.py").read_text(encoding="utf-8")
        self.assertNotIn('F.data == "refresh"', runtime_source)
        self.assertNotIn("async def refresh_handler(", runtime_source)
        self.assertNotIn("refresh", _ADOPT_CALLBACKS)

        for rel in (
            "runtime/production_runtime.py",
            "ui_polish.py",
            "production_bot_ui.py",
            "operator_hmi.py",
            "operator_dashboard.py",
        ):
            source = (ROOT / rel).read_text(encoding="utf-8")
            self.assertNotIn('callback_data="refresh"', source, rel)


if __name__ == "__main__":
    unittest.main()
