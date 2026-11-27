"""Fake-only behavioral coverage for the single logger outage transition."""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import runtime.production_runtime as runtime
from application.link_outage_use_case import transition_link_outage
from production_controller import create_production_charge_host


class _EndLogger(Exception):
    pass


class LinkOutageUseCaseTests(unittest.IsolatedAsyncioTestCase):
    async def _run_failure(self, *, read_error=None, cycle_error=None, off_result=True):
        controller = create_production_charge_host(object())
        controller.current_stage = controller.STAGE_MAIN
        controller._last_known_output_on = True
        live = {"switch": "on"}
        owner = SimpleNamespace(
            get_all_live=AsyncMock(side_effect=read_error) if read_error else AsyncMock(return_value=live),
        )
        port = SimpleNamespace(request_emergency_off=AsyncMock(return_value=off_result))
        stop = Mock(wraps=controller.stop)
        controller.stop = stop
        logger = Mock()
        replacements = {
            "runtime_safety_guard": owner,
            "charge_controller": controller,
            "_runtime_execution_port": Mock(return_value=port),
            "_charge_notify": Mock(),
            "log_event": Mock(),
            "logger": logger,
            "link_failure_streak": 0,
            "link_lost_alert_sent": False,
            "LINK_FAILURE_NOTIFY_THRESHOLD": 1,
        }
        if cycle_error is not None:
            replacements["observe_data_logger_cycle"] = Mock(side_effect=cycle_error)
        with patch.multiple(runtime, create=True, **replacements), \
             patch.object(runtime.asyncio, "sleep", side_effect=_EndLogger), \
             patch.object(runtime.time, "time", return_value=1234.0):
            try:
                await runtime.data_logger()
            except _EndLogger:
                pass
        return controller, owner, port, stop, replacements["_charge_notify"], replacements["log_event"], logger

    async def test_initial_transport_outage_uses_threshold_notice_and_never_stops(self):
        controller, owner, port, stop, notify, _, _ = await self._run_failure(
            read_error=ConnectionError("edge disconnected"),
        )
        owner.get_all_live.assert_awaited_once()
        port.request_emergency_off.assert_not_awaited()
        stop.assert_not_called()
        notify.assert_called_once()
        self.assertTrue(controller._was_unavailable)

    async def test_recoverable_cycle_readback_preserves_session_without_off(self):
        controller, _, port, stop, notify, _, logger = await self._run_failure(
            cycle_error=RuntimeError("OFF command accepted but switch state was not confirmed"),
        )
        port.request_emergency_off.assert_not_awaited()
        stop.assert_not_called()
        notify.assert_called_once()
        logger.warning.assert_called_once()
        self.assertTrue(controller._was_unavailable)

    async def test_unexpected_cycle_stops_only_after_emergency_off_result(self):
        for off_result in (True, False):
            with self.subTest(off_result=off_result):
                controller, _, port, stop, _, events, logger = await self._run_failure(
                    cycle_error=RuntimeError("temperature safety verification failed"),
                    off_result=off_result,
                )
                port.request_emergency_off.assert_awaited_once()
                self.assertEqual(stop.call_count, 1 if off_result else 0)
                self.assertEqual(
                    any(call.args[-1] == "LINK_LOST_DURING_CHARGE" for call in events.call_args_list),
                    off_result,
                )
                if not off_result:
                    logger.exception.assert_called_once()
                    self.assertTrue(controller.is_active)


class LinkOutageTransitionTests(unittest.TestCase):
    def test_categories_share_only_the_existing_recoverable_incident_transition(self):
        for category in ("initial_read", "cycle_readback"):
            with self.subTest(category=category):
                result = transition_link_outage(
                    category=category, recoverable_link_error=True,
                    failure_streak=2, alert_sent=False, last_known_output_on=True,
                    session_active=True, notification_threshold=3,
                )
                self.assertEqual(result.failure_streak, 3)
                self.assertTrue(result.notify_repeated_outage)
                self.assertFalse(result.request_emergency_off)


if __name__ == "__main__":
    unittest.main()
