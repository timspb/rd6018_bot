import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from runtime import production_runtime as runtime

from application.charge_session_tick import run_charge_session_tick
from production_controller import create_production_charge_host


class DummyHass:
    pass


class V2NotificationIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def _assert_captured_notification_recipient(self, *, fail_html_send):
        saved_globals = (
            runtime.last_chat_id,
            runtime.last_notification_signature,
            runtime.last_notification_at,
            runtime.NOTIFY_CHAT_ID,
            runtime.ALLOWED_CHAT_IDS,
            runtime.bot,
        )
        scheduled = []
        sends = AsyncMock()
        if fail_html_send:
            sends.side_effect = [RuntimeError("HTML send failed"), None]

        def defer_task(coroutine):
            scheduled.append(coroutine)
            return coroutine

        try:
            runtime.last_chat_id = None
            runtime.last_notification_signature = ""
            runtime.last_notification_at = 0.0
            runtime.NOTIFY_CHAT_ID = 101
            runtime.ALLOWED_CHAT_IDS = []
            runtime.bot = SimpleNamespace(send_message=sends)
            # PanelLast is installed only after production composition. If
            # present, keep this test scoped to notification delivery; when
            # absent, the standalone sender has no dashboard publication.
            panel_manager = getattr(runtime, "terminal_panel_manager", None)
            panel_guard = (
                patch.object(panel_manager, "in_workspace", return_value=True)
                if panel_manager is not None else nullcontext()
            )
            with patch.object(runtime.asyncio, "create_task", side_effect=defer_task), panel_guard:
                runtime._charge_notify("recipient capture regression")
                self.assertEqual(len(scheduled), 1)
                runtime.last_chat_id = 202
                await scheduled.pop()  # Await the deferred task; no task is left behind.

            recipients = [call.args[0] for call in sends.await_args_list]
            self.assertEqual(recipients, [101] * (2 if fail_html_send else 1))
            self.assertNotIn(202, [call.args[0] for call in sends.await_args_list])
            if fail_html_send:
                self.assertEqual(sends.await_args_list[0].kwargs.get("parse_mode"), runtime.ParseMode.HTML)
                self.assertEqual(sends.await_args_list[1].kwargs, {})
            else:
                self.assertEqual(sends.await_args_list[0].kwargs.get("parse_mode"), runtime.ParseMode.HTML)
        finally:
            for coroutine in scheduled:
                coroutine.close()
            (
                runtime.last_chat_id,
                runtime.last_notification_signature,
                runtime.last_notification_at,
                runtime.NOTIFY_CHAT_ID,
                runtime.ALLOWED_CHAT_IDS,
                runtime.bot,
            ) = saved_globals

    async def test_notification_uses_recipient_captured_before_scheduled_task_runs(self):
        await self._assert_captured_notification_recipient(fail_html_send=False)

    async def test_plaintext_fallback_uses_same_captured_recipient(self):
        await self._assert_captured_notification_recipient(fail_html_send=True)

    async def test_managed_profile_refreshes_legacy_hourly_clock_before_scaffold_tick(self):
        controller = create_production_charge_host(DummyHass())
        controller.battery_type = controller.PROFILE_CA
        controller.current_stage = controller.STAGE_MAIN
        controller._last_hourly_report = 0.0

        with patch(
            "application.charge_session_tick._run_charge_session_tick_body",
            new=AsyncMock(return_value={}),
        ) as session_body:
            result = await run_charge_session_tick(controller,
                14.7,
                0.1,
                23.0,
                True,
                1.0,
                output_is_on=True,
                is_cc=False,
            )

        self.assertEqual(result, {})
        self.assertGreater(controller._last_hourly_report, 0.0)
        session_body.assert_awaited_once()

    async def test_custom_profile_retains_legacy_hourly_reporting_contract(self):
        controller = create_production_charge_host(DummyHass())
        controller.battery_type = controller.PROFILE_CUSTOM
        controller.current_stage = controller.STAGE_MAIN
        controller._last_hourly_report = 0.0

        with patch(
            "application.charge_session_tick._run_charge_session_tick_body",
            new=AsyncMock(return_value={}),
        ):
            await run_charge_session_tick(controller,
                14.4,
                1.0,
                23.0,
                True,
                1.0,
                output_is_on=True,
                is_cc=False,
            )

        self.assertEqual(controller._last_hourly_report, 0.0)


if __name__ == "__main__":
    unittest.main()
