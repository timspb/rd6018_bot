from __future__ import annotations

import unittest
from types import SimpleNamespace

from application.operator_snapshot import snapshot_from_mapping
from operator_dashboard import install_operator_graph_dashboard


class _Interface:
    async def get_operator_snapshot(self):
        return snapshot_from_mapping({
            "state": "IDLE",
            "battery": {"label": "AGM70"},
            "telemetry": {"voltage": 12.8, "current": 0.0},
            "safety": {"allowed": True},
            "output": {"enabled": False},
            "charge": {"stage": "IDLE"},
        })


class _Bot:
    def __init__(self):
        self.edited = []

    async def edit_message_caption(self, **kwargs):
        self.edited.append(kwargs)


class _App:
    operator_interface = _Interface()
    bot = _Bot()
    ParseMode = SimpleNamespace(HTML="HTML")
    InlineKeyboardMarkup = object
    logger = SimpleNamespace(error=lambda *args: None, warning=lambda *args: None)
    user_dashboard = {}
    chat_dashboard = {}


class OperatorPanelIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_refresh_uses_interface_and_existing_message(self):
        app = _App()
        app._operator_graph_dashboard_installed = False
        # The real installer composes the existing keyboard; this test isolates
        # the read-path contract and supplies the minimal keyboard dependencies.
        import operator_dashboard
        original = operator_dashboard._main_graph_markup
        operator_dashboard._main_graph_markup = lambda app, state, user_id: None
        try:
            install_operator_graph_dashboard(app)
            await app._refresh_operator_panel(1, 2, 99)
        finally:
            operator_dashboard._main_graph_markup = original
        self.assertEqual(len(app.bot.edited), 1)
        self.assertEqual(app.bot.edited[0]["message_id"], 99)
        self.assertIn("12.80", app.bot.edited[0]["caption"])


if __name__ == "__main__":
    unittest.main()
