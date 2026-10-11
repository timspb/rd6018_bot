from __future__ import annotations

import unittest
from types import SimpleNamespace

from application.operator_actions import OperatorActionsView
from application.operator_snapshot import snapshot_from_mapping
from operator_hmi import install_operator_hmi
from runtime.ui.telegram.home import install_home_command
from runtime.ui.telegram.charge import CHARGE_CALLBACK_DATA


class _Router:
    def __init__(self):
        self.message_handlers = []

    def message(self, *_args, **_kwargs):
        def decorator(handler):
            self.message_handlers.append(handler)
            return handler
        return decorator

    def callback_query(self, *_args, **_kwargs):
        return lambda handler: handler


class _Bot:
    def __init__(self):
        self.sent = []

    async def send_message(self, *args, **kwargs):
        self.sent.append((args, kwargs))
        return SimpleNamespace(message_id=101)


class _Interface:
    def __init__(self):
        self.snapshot = snapshot_from_mapping({
            "state": "IDLE",
            "battery": {"label": "AGM70"},
            "telemetry": {"voltage": 12.8, "current": 0.0},
            "safety": {"allowed": True},
            "output": {"enabled": False},
            "charge": {"stage": "IDLE"},
        })
        self.action_snapshot = None

    async def get_operator_snapshot(self):
        return self.snapshot

    async def get_operator_actions(self, *, snapshot):
        self.action_snapshot = snapshot
        # This is the production provider's semantic result for IDLE.  The
        # dashboard must render it from the same snapshot as its text.
        return OperatorActionsView.for_state(
            snapshot.state,
            safety_allowed=snapshot.snapshot.safety.allowed,
        )


class _App:
    def __init__(self):
        self.router = _Router()
        self.bot = _Bot()
        self.ParseMode = SimpleNamespace(HTML="HTML")
        self.operator_interface = _Interface()
        self.user_dashboard = {}
        self.chat_dashboard = {}

    async def _check_chat_and_respond(self, _event):
        return True


class OperatorHmiHomeTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_dashboard_renders_charge_navigation_from_snapshot(self):
        app = _App()
        install_operator_hmi(app)

        message_id = await app._build_and_send_dashboard(chat_id=10, user_id=20)

        self.assertEqual(message_id, 101)
        self.assertIs(app.operator_interface.action_snapshot, app.operator_interface.snapshot)
        markup = app.bot.sent[0][1]["reply_markup"]
        callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
        self.assertIn(CHARGE_CALLBACK_DATA, callbacks)
        self.assertNotIn("operator_details", callbacks)
        self.assertIn("operator_refresh", callbacks)

    async def test_real_start_route_preserves_hands_off_and_exposes_safe_navigation(self):
        app = _App()
        app.operator_interface.snapshot = snapshot_from_mapping({
            "state": "HANDS_OFF",
            "charge": {
                "stage": "RD6018 · РУЧНОЕ УПРАВЛЕНИЕ",
                "program": "external",
                "waiting_for": "RD свободен от Pb-автоматики",
            },
            "safety": {"allowed": True},
            "output": {"enabled": False},
        })
        install_operator_hmi(app)
        install_home_command(app, render_home=app._build_and_send_dashboard)
        start = next(handler for handler in app.router.message_handlers if handler.__name__ == "_home_command")
        await start(SimpleNamespace(
            from_user=SimpleNamespace(id=20),
            chat=SimpleNamespace(id=10),
        ))

        text = app.bot.sent[0][0][1]
        markup = app.bot.sent[0][1]["reply_markup"]
        callbacks = {button.callback_data for row in markup.inline_keyboard for button in row}
        self.assertIn("RD свободен от Pb-автоматики", text)
        self.assertIn(CHARGE_CALLBACK_DATA, callbacks)
        self.assertIn("rd_hands_off_disable", callbacks)
        self.assertIn("operator_refresh", callbacks)
        self.assertNotIn("rd_hands_off_output_off", callbacks)


if __name__ == "__main__":
    unittest.main()
