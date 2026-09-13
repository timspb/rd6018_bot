import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from aiogram import Bot
from aiogram.enums import ChatType
from aiogram.types import CallbackQuery, Chat, Message, Update, User

import bot as app
from rd_control_mode import RdControlMode
from soft_watchdog_containment import SoftWatchdogIncident, soft_watchdog_poll_once


class AutonomousRuntimeCompositionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        if app.router.parent_router is None:
            app.dp.include_router(app.router)
        self.manager = app.rd_control_mode_manager
        self._mode = self.manager.mode
        self._edge_autonomous = self.manager._edge_autonomous

    def tearDown(self):
        self.manager.mode = self._mode
        self.manager._edge_autonomous = self._edge_autonomous

    @staticmethod
    def _callback_update(data: str) -> Update:
        operator = User(id=1, is_bot=False, first_name="Operator")
        message = Message(
            message_id=611,
            date=datetime.now(timezone.utc),
            chat=Chat(id=1, type=ChatType.PRIVATE),
            from_user=operator,
            text="old HANDS_OFF panel",
        )
        return Update(
            update_id=8101,
            callback_query=CallbackQuery(
                id="autonomous-stale-off",
                from_user=operator,
                chat_instance="autonomous-test",
                message=message,
                data=data,
            ),
        )

    async def test_stale_hands_off_output_off_callback_is_non_actuating_in_autonomous(self):
        """A pre-AUTONOMOUS Telegram button must not retain physical OFF authority."""
        self.manager.mode = RdControlMode.HANDS_OFF
        self.manager._edge_autonomous = True
        ensure_off = AsyncMock(return_value=True)
        disarm = AsyncMock(return_value=None)
        telegram_calls = []

        async def fake_telegram_api(_bot, method, *args, **kwargs):
            del args, kwargs
            telegram_calls.append(type(method).__name__)
            return True

        with (
            patch.object(app, "_check_chat_and_respond", new=AsyncMock(return_value=True)),
            patch.object(self.manager.guard, "_ensure_output_off", new=ensure_off),
            patch.object(self.manager.guard, "_disarm_edge_lease_best_effort", new=disarm),
            patch.object(Bot, "__call__", new=fake_telegram_api),
        ):
            await app.dp.feed_update(
                app.bot,
                self._callback_update("rd_hands_off_output_off"),
            )

        self.assertEqual(ensure_off.await_count, 0)
        self.assertEqual(disarm.await_count, 0)
        self.assertIn("AnswerCallbackQuery", telegram_calls)

    async def test_autonomous_ha_outage_does_not_invoke_pb_hard_stop(self):
        """Exercise the composed app watchdog boundary under explicit AUTONOMOUS."""
        self.manager.mode = RdControlMode.HANDS_OFF
        self.manager._edge_autonomous = True
        incident = SoftWatchdogIncident(active=True, logged=True, last_attempt_at=1.0)
        hard_stop = AsyncMock()
        old_last_ok = app.last_ha_ok_time
        old_timeout = app.SOFT_WATCHDOG_TIMEOUT
        old_controller_active = bool(app.charge_controller.is_active)
        old_last_known = bool(getattr(app.charge_controller, "_last_known_output_on", False))
        try:
            app.last_ha_ok_time = 100.0
            app.SOFT_WATCHDOG_TIMEOUT = 180.0
            app.charge_controller.is_active = True
            app.charge_controller._last_known_output_on = True
            with patch.object(app, "_hard_stop_charge", new=hard_stop):
                await soft_watchdog_poll_once(app, incident, now=700.0)
        finally:
            app.last_ha_ok_time = old_last_ok
            app.SOFT_WATCHDOG_TIMEOUT = old_timeout
            app.charge_controller.is_active = old_controller_active
            app.charge_controller._last_known_output_on = old_last_known

        self.assertEqual(hard_stop.await_count, 0)
        self.assertFalse(incident.active)


if __name__ == "__main__":
    unittest.main()
