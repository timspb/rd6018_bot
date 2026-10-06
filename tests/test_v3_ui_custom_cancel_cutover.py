from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest

from runtime.ui.actions import UIAction
from runtime.ui.telegram.custom import (
    CUSTOM_CANCEL_CALLBACK_DATA,
    install_custom_cancel_route,
)
from runtime.ui.telegram.renderer import action_from_callback_data
from telegram_panel import _TERMINAL_CALLBACKS, _is_workspace_callback


ROOT = Path(__file__).resolve().parents[1]


class _RouterGroup:
    def __init__(self):
        self.handlers = []

    def __call__(self, _filter):
        def decorate(func):
            self.handlers.append(func)
            return func
        return decorate


class _Router:
    def __init__(self):
        self.callback_query = _RouterGroup()


class _Call:
    def __init__(self):
        self.from_user = SimpleNamespace(id=7)
        self.answers = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


class _App:
    def __init__(self):
        self.router = _Router()

    async def _check_chat_and_respond(self, _event):
        return True


class V3CustomCancelCutoverTests(unittest.TestCase):
    def test_callback_is_canonical_terminal_navigation(self):
        self.assertEqual(
            action_from_callback_data(CUSTOM_CANCEL_CALLBACK_DATA),
            UIAction.CANCEL_CUSTOM,
        )
        self.assertIn(CUSTOM_CANCEL_CALLBACK_DATA, _TERMINAL_CALLBACKS)
        self.assertFalse(_is_workspace_callback(CUSTOM_CANCEL_CALLBACK_DATA))
        self.assertFalse(_is_workspace_callback("custom_cancel"))

    def test_historical_custom_cancel_route_and_payload_are_removed(self):
        runtime = (ROOT / "runtime" / "production_runtime.py").read_text(encoding="utf-8")
        panel = (ROOT / "telegram_panel.py").read_text(encoding="utf-8")
        self.assertNotIn('F.data == "custom_cancel"', runtime)
        self.assertNotIn("async def custom_mode_cancel(", runtime)
        self.assertNotIn('callback_data="custom_cancel"', runtime)
        self.assertIn("CUSTOM_CANCEL_CALLBACK_DATA", runtime)
        self.assertNotIn('"custom_cancel"', panel)

    def test_canonical_adapter_has_no_historical_or_physical_imports(self):
        source = (ROOT / "runtime" / "ui" / "telegram" / "custom.py").read_text(
            encoding="utf-8"
        )
        for forbidden in (
            "runtime.v2_runtime",
            "charge_logic",
            "charge_controller",
            "hass_api",
            "runtime_safety",
            "safe_output",
            "esphome",
        ):
            self.assertNotIn(forbidden, source)

    def test_production_composition_injects_state_clear_and_home_navigation(self):
        source = (ROOT / "bot.py").read_text(encoding="utf-8")
        self.assertIn("install_custom_cancel_route(", source)
        self.assertIn("cancel_state=_legacy._cancel_custom_mode_state", source)
        self.assertIn("home_handler=_legacy._operator_home_handler", source)


class V3CustomCancelTelegramTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancel_clears_state_and_delegates_home(self):
        app = _App()
        cleared = []
        homes = []

        async def home(call):
            homes.append(call)

        install_custom_cancel_route(
            app,
            cancel_state=lambda user: cleared.append(user),
            home_handler=home,
        )
        call = _Call()
        await app._v3_custom_cancel_handler(call)

        self.assertEqual(cleared, [7])
        self.assertEqual(homes, [call])
        self.assertTrue(call.answers)


if __name__ == "__main__":
    unittest.main()
