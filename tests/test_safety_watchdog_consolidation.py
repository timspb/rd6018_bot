"""Policy and execution tests for consolidated production safety monitoring."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from runtime.safety.communication_watchdog import communication_shutdown_due
from runtime.safety.watchdog_runtime import communication_watchdog_poll_once


class CommunicationWatchdogTests(unittest.IsolatedAsyncioTestCase):
    def test_300s_boundary_and_native_grace(self):
        base = dict(now_epoch_s=400.0, last_controller_update_epoch_s=100.0,
                    now_monotonic_s=450.0, timeout_s=300.0)
        self.assertTrue(communication_shutdown_due({"switch": "on"}, **base))
        self.assertFalse(communication_shutdown_due({"switch": "off"}, **base))
        self.assertFalse(communication_shutdown_due(
            {"switch": "on", "_native_link_outage_since": 200.0}, **base))
        self.assertFalse(communication_shutdown_due(
            {"switch": "on", "_managed_telemetry_recovery_pending": True}, **base))
        self.assertFalse(communication_shutdown_due(
            {"switch": "on"}, guard_recovery_active=True, **base))
        self.assertFalse(communication_shutdown_due(
            {"switch": "on"}, **{**base, "now_epoch_s": 399.0}))
        self.assertTrue(communication_shutdown_due(
            {"switch": "on", "_native_link_outage_since": 149.0}, **base))

    def test_invalid_or_unknown_evidence_never_creates_shutdown_authority(self):
        base = dict(now_epoch_s=400.0, last_controller_update_epoch_s=100.0,
                    now_monotonic_s=450.0)
        self.assertFalse(communication_shutdown_due({"switch": "unknown"}, **base))
        self.assertFalse(communication_shutdown_due(
            {"switch": "on"}, **{**base, "last_controller_update_epoch_s": 0}))
        self.assertFalse(communication_shutdown_due(
            {"switch": "on"}, **{**base, "now_epoch_s": float("nan")}))

    async def test_off_only_after_timeout_and_single_execution_owner(self):
        events = []
        controller = SimpleNamespace(last_update_time=100.0, current_stage="MIX")
        app = SimpleNamespace(
            charge_controller=controller,
            hass=SimpleNamespace(get_all_live=AsyncMock(return_value={
                "switch": "on", "voltage": 16.5, "current": 0.1,
                "temp_ext": 25.0, "ah": 4.0,
            })),
            runtime_safety_guard=SimpleNamespace(telemetry_recovery_active=False),
            WATCHDOG_TIMEOUT=300.0,
            logger=SimpleNamespace(critical=lambda *args: events.append("critical")),
            log_event=lambda *args: events.append(args[-1]),
            _hard_stop_charge=AsyncMock(),
        )
        self.assertFalse(await communication_watchdog_poll_once(
            app, now_epoch_s=399.0, now_monotonic_s=700.0))
        app._hard_stop_charge.assert_not_awaited()
        self.assertTrue(await communication_watchdog_poll_once(
            app, now_epoch_s=400.0, now_monotonic_s=700.0))
        app._hard_stop_charge.assert_awaited_once()
        self.assertEqual(events, ["critical", "WATCHDOG_TIMEOUT"])


if __name__ == "__main__":
    unittest.main()

class SafetyMonitorLoopTests(unittest.IsolatedAsyncioTestCase):
    async def test_latched_soft_watchdog_suppresses_competing_communication_off(self):
        import asyncio
        from unittest.mock import patch
        from runtime.safety.watchdog_runtime import run_safety_watchdogs
        calls = 0
        async def bounded_sleep(_seconds):
            nonlocal calls
            calls += 1
            if calls >= 3:
                raise asyncio.CancelledError
        async def soft_incident(_app, incident):
            incident.active = True
            incident.logged = True
        app = SimpleNamespace(logger=SimpleNamespace(error=lambda *args: None))
        communication = AsyncMock()
        with patch("runtime.safety.watchdog_runtime.COMM_POLL_S", 0.0), \
             patch("runtime.safety.watchdog_runtime.asyncio.sleep", bounded_sleep), \
             patch("runtime.safety.watchdog_runtime.soft_watchdog_poll_once", soft_incident), \
             patch("runtime.safety.watchdog_runtime.communication_watchdog_poll_once", communication):
            with self.assertRaises(asyncio.CancelledError):
                await run_safety_watchdogs(app)
        communication.assert_not_awaited()

    async def test_healthy_soft_watchdog_allows_communication_policy(self):
        import asyncio
        from unittest.mock import patch
        from runtime.safety.watchdog_runtime import run_safety_watchdogs
        calls = 0
        async def bounded_sleep(_seconds):
            nonlocal calls
            calls += 1
            if calls >= 2:
                raise asyncio.CancelledError
        async def no_incident(_app, _incident):
            return None
        app = SimpleNamespace(logger=SimpleNamespace(error=lambda *args: None))
        communication = AsyncMock(return_value=False)
        with patch("runtime.safety.watchdog_runtime.COMM_POLL_S", 0.0), \
             patch("runtime.safety.watchdog_runtime.asyncio.sleep", bounded_sleep), \
             patch("runtime.safety.watchdog_runtime.soft_watchdog_poll_once", no_incident), \
             patch("runtime.safety.watchdog_runtime.communication_watchdog_poll_once", communication):
            with self.assertRaises(asyncio.CancelledError):
                await run_safety_watchdogs(app)
        communication.assert_awaited_once()
