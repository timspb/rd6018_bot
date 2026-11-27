import asyncio
import os
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest import mock

import manual_mode
import manual_runtime
from manual_mode import ManualChargeRequest, ManualSessionState
from manual_runtime import ProductionManualSessionManager


class FakeHass:
    def __init__(self):
        self.live = {
            "battery_voltage": 14.0,
            "current": 1.0,
            "temp_ext": 25.0,
            "temp_int": 30.0,
            "switch": "off",
            "is_cv": True,
            "is_cc": False,
            "ovp_triggered": False,
            "ocp_triggered": False,
        }
        self.enable_requests = []
        self.off_calls = 0
        self.enable_raises = False
        self.enable_result = True
        self.enable_detail = ""
        self.off_result = True
        self.off_raises = False

    async def safe_enable_output(self, **kwargs):
        self.enable_requests.append(dict(kwargs))
        if self.enable_raises:
            raise RuntimeError("synthetic safe-enable exception")
        if not self.enable_result:
            return SimpleNamespace(enabled=False, detail=self.enable_detail)
        self.live["switch"] = "on"
        return SimpleNamespace(enabled=True, detail="")

    async def turn_off(self, entity_id=None):
        self.off_calls += 1
        if self.off_raises:
            raise RuntimeError("synthetic OFF exception")
        if not self.off_result:
            return False
        self.live["switch"] = "off"
        return True

    async def get_all_live(self):
        return dict(self.live)


class DummyController:
    is_active = False


class ManualRuntimeV2Tests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.session_file = os.path.join(self.tempdir.name, "manual.json")
        self.hass = FakeHass()
        self.manual_off_clear_calls = 0

        def clear_manual_off():
            self.manual_off_clear_calls += 1
            self.app.manual_off_voltage = None
            self.app.manual_off_voltage_le = None
            self.app.manual_off_current = None
            self.app.manual_off_current_ge = None
            self.app.manual_off_time_sec = None
            self.app.manual_off_start_time = 0.0

        self.app = SimpleNamespace(
            hass=self.hass,
            charge_controller=DummyController(),
            manual_off_voltage=None,
            manual_off_voltage_le=None,
            manual_off_current=None,
            manual_off_current_ge=None,
            manual_off_time_sec=None,
            manual_off_start_time=0.0,
            _clear_manual_off=clear_manual_off,
        )

    async def asyncTearDown(self):
        manager = getattr(self.app, "manual_session_manager", None)
        if manager is not None and manager._task is not None:
            manager._task.cancel()
            try:
                await manager._task
            except asyncio.CancelledError:
                pass
        self.tempdir.cleanup()

    def _manager(self):
        manager = ProductionManualSessionManager(self.app, session_file=self.session_file)
        self.app.manual_session_manager = manager
        return manager

    def test_restart_reach_read_uses_manual_session_store_owner(self):
        manager = self._manager()
        manager.request = ManualChargeRequest(14.7, 2.0)
        manager.state = ManualSessionState.ACTIVE
        manager.started_at = time.time()
        manager.reach_voltage_v = 15.2
        manager.reach_current_a = 0.8
        manager._persist()

        original_reader = manual_runtime.read_manual_session_document
        original_base_reader = manual_mode.read_manual_session_document
        original_writer = manual_mode.write_manual_session_document
        with mock.patch.object(
            manual_runtime,
            "read_manual_session_document",
            wraps=original_reader,
        ) as reader, mock.patch.object(
            manual_mode,
            "read_manual_session_document",
            wraps=original_base_reader,
        ) as base_reader, mock.patch.object(
            manual_mode,
            "write_manual_session_document",
            wraps=original_writer,
        ) as writer:
            restored = ProductionManualSessionManager(
                self.app,
                session_file=self.session_file,
            )

        reader.assert_called_once_with(self.session_file)
        base_reader.assert_not_called()
        writer.assert_called_once()
        self.assertEqual(restored.state, ManualSessionState.INTERRUPTED)
        self.assertEqual(restored.reach_voltage_v, 15.2)
        self.assertEqual(restored.reach_current_a, 0.8)

    def test_restart_corrupt_document_uses_one_store_read_without_write_or_enable(self):
        from pathlib import Path
        Path(self.session_file).write_text('{"state":', encoding="utf-8")
        with mock.patch.object(
            manual_runtime, "read_manual_session_document",
            wraps=manual_runtime.read_manual_session_document,
        ) as reader, mock.patch.object(
            manual_mode, "read_manual_session_document",
            side_effect=AssertionError("base restore must not reread"),
        ) as base_reader, mock.patch.object(
            manual_mode, "write_manual_session_document",
            side_effect=AssertionError("invalid source must not be rewritten"),
        ) as writer:
            restored = self._manager()
        reader.assert_called_once_with(self.session_file)
        base_reader.assert_not_called()
        writer.assert_not_called()
        self.assertEqual(restored.state, ManualSessionState.IDLE)
        self.assertIsNone(restored.reach_voltage_v)
        self.assertIsNone(restored.reach_current_a)
        self.assertEqual(self.hass.enable_requests, [])
        self.assertEqual(Path(self.session_file).read_text(encoding="utf-8"), '{"state":')

    def test_restart_stopped_document_reads_once_without_terminal_rewrite(self):
        from pathlib import Path
        import json
        document = {
            "version": 2, "state": "stopped",
            "request": None, "reach_voltage_v": 15.0, "reach_current_a": 1.25,
        }
        Path(self.session_file).write_text(json.dumps(document), encoding="utf-8")
        with mock.patch.object(
            manual_runtime, "read_manual_session_document",
            wraps=manual_runtime.read_manual_session_document,
        ) as reader, mock.patch.object(
            manual_mode, "read_manual_session_document",
            side_effect=AssertionError("unexpected base read"),
        ) as base_reader, mock.patch.object(
            manual_mode, "write_manual_session_document",
            side_effect=AssertionError("stopped state is not re-committed"),
        ) as writer:
            restored = self._manager()
        reader.assert_called_once_with(self.session_file)
        base_reader.assert_not_called()
        writer.assert_not_called()
        self.assertEqual(restored.state, ManualSessionState.IDLE)
        self.assertEqual(restored.reach_voltage_v, 15.0)
        self.assertEqual(restored.reach_current_a, 1.25)
        self.assertEqual(self.hass.enable_requests, [])

    async def test_manual_observer_reads_through_managed_safety_owner(self):
        live = {
            "battery_voltage": 14.0,
            "current": 1.0,
            "temp_ext": 25.0,
            "temp_int": 30.0,
            "switch": "on",
            "is_cv": True,
            "is_cc": False,
        }
        safety_owner = SimpleNamespace(
            get_all_live=mock.AsyncMock(return_value=dict(live)),
        )
        self.app.runtime_safety_guard = safety_owner
        self.hass.get_all_live = mock.AsyncMock(
            side_effect=AssertionError("Manual must not bypass ManagedRuntimeSafetyGuard")
        )
        manager = self._manager()
        manager.request = ManualChargeRequest(14.7, 2.0)
        manager.state = ManualSessionState.ACTIVE
        manager.started_at = time.time()

        await manager.observe_once()

        self.assertIs(manager.execution_port._execution_owner, safety_owner)
        self.assertIs(manager.execution_boundary.execution_port, manager.execution_port)
        self.assertEqual(safety_owner.get_all_live.await_count, 2)
        self.hass.get_all_live.assert_not_awaited()

    async def test_active_manual_reconfiguration_is_verified_off_then_fresh_enable(self):
        manager = self._manager()
        self.assertTrue(await manager.start(ManualChargeRequest(14.7, 4.0)))
        self.assertEqual(manager.state, ManualSessionState.ACTIVE)

        self.assertTrue(await manager.replace(ManualChargeRequest(16.5, 1.5)))
        self.assertEqual(manager.state, ManualSessionState.ACTIVE)
        self.assertGreaterEqual(self.hass.off_calls, 1)
        self.assertEqual(len(self.hass.enable_requests), 2)
        self.assertAlmostEqual(self.hass.enable_requests[-1]["voltage_v"], 16.5)
        self.assertAlmostEqual(self.hass.enable_requests[-1]["current_a"], 1.5)

    async def test_denied_safe_enable_with_unconfirmed_off_stays_managed(self):
        manager = self._manager()
        self.hass.enable_result = False
        self.hass.enable_detail = "programming failed; output OFF was not confirmed"
        self.hass.live["switch"] = "on"

        enabled = await manager.start(ManualChargeRequest(14.7, 2.0))

        self.assertFalse(enabled)
        self.assertEqual(manager.state, ManualSessionState.ARMING)
        self.assertTrue(manager.is_active)
        self.assertIn("output_off_unconfirmed", manager.stop_reason)

    async def test_denied_safe_enable_after_confirmed_cleanup_becomes_failed(self):
        manager = self._manager()
        self.hass.enable_result = False
        self.hass.enable_detail = "recipe preflight denied"

        enabled = await manager.start(ManualChargeRequest(14.7, 2.0))

        self.assertFalse(enabled)
        self.assertEqual(manager.state, ManualSessionState.FAILED)
        self.assertFalse(manager.is_active)

    async def test_safe_enable_exception_with_unconfirmed_off_stays_managed(self):
        manager = self._manager()
        self.hass.enable_raises = True
        self.hass.off_result = False
        self.hass.live["switch"] = "on"

        enabled = await manager.start(ManualChargeRequest(14.7, 2.0))

        self.assertFalse(enabled)
        self.assertEqual(manager.state, ManualSessionState.ARMING)
        self.assertTrue(manager.is_active)
        self.assertIn("output_off_unconfirmed", manager.stop_reason)
        self.assertGreaterEqual(self.hass.off_calls, 1)

    async def test_safe_enable_exception_with_confirmed_off_becomes_failed(self):
        manager = self._manager()
        self.hass.enable_raises = True
        self.hass.live["switch"] = "on"

        enabled = await manager.start(ManualChargeRequest(14.7, 2.0))

        self.assertFalse(enabled)
        self.assertEqual(manager.state, ManualSessionState.FAILED)
        self.assertFalse(manager.is_active)
        self.assertEqual(self.hass.live["switch"], "off")

    async def test_stop_with_unconfirmed_off_remains_active_containment(self):
        manager = self._manager()
        manager.request = ManualChargeRequest(14.7, 2.0)
        manager.state = ManualSessionState.ACTIVE
        manager.started_at = time.time()
        self.hass.live["switch"] = "on"
        self.hass.off_result = False

        confirmed = await manager.stop("operator_stop")

        self.assertFalse(confirmed)
        self.assertEqual(manager.state, ManualSessionState.ARMING)
        self.assertTrue(manager.is_active)
        self.assertIn("output_off_unconfirmed", manager.stop_reason)

    async def test_operator_stop_records_terminal_transition_after_verified_off(self):
        manager = self._manager()
        manager.request = ManualChargeRequest(14.7, 2.0)
        manager.state = ManualSessionState.ACTIVE
        manager.started_at = time.time()
        self.hass.live["switch"] = "on"

        with self.assertLogs("rd6018.manual", level="INFO") as captured:
            confirmed = await manager.stop("operator_stop")

        self.assertTrue(confirmed)
        self.assertEqual(manager.state, ManualSessionState.STOPPED)
        self.assertTrue(any("old=active new=stopped reason=operator_stop" in line for line in captured.output))

    async def test_cooling_off_false_remains_managed_containment(self):
        manager = self._manager()
        manager.request = ManualChargeRequest(14.7, 2.0)
        manager.state = ManualSessionState.ACTIVE
        manager.started_at = time.time()
        self.hass.live["switch"] = "on"
        self.hass.live["temp_ext"] = 40.0
        self.hass.off_result = False

        await manager.observe_once()

        self.assertEqual(manager.state, ManualSessionState.ARMING)
        self.assertTrue(manager.is_active)
        self.assertEqual(manager.stop_reason, "cooling_output_off_unconfirmed")

    async def test_cooling_resume_denied_with_unconfirmed_off_stays_managed(self):
        manager = self._manager()
        manager.request = ManualChargeRequest(14.7, 2.0)
        manager.state = ManualSessionState.COOLING
        manager.started_at = time.time() - 600
        manager.cooling_started_at = time.time() - 300
        self.hass.live["switch"] = "off"
        self.hass.live["temp_ext"] = 35.0
        self.hass.enable_result = False
        self.hass.enable_detail = "post-enable failed; output OFF was not confirmed"

        await manager.observe_once()

        self.assertEqual(manager.state, ManualSessionState.ARMING)
        self.assertTrue(manager.is_active)
        self.assertIn("output_off_unconfirmed", manager.stop_reason)

    async def test_exact_voltage_reach_detects_crossing_between_samples(self):
        manager = self._manager()
        manager.request = ManualChargeRequest(16.5, 1.5)
        manager.reach_voltage_v = 15.0
        manager.state = ManualSessionState.ACTIVE
        manager.started_at = time.time()
        manager._previous_voltage_v = 14.9
        manager._previous_current_a = 1.5
        self.hass.live["switch"] = "on"
        self.hass.live["battery_voltage"] = 15.1

        await manager.observe_once()
        self.assertEqual(manager.state, ManualSessionState.STOPPED)
        self.assertEqual(manager.stop_reason, "manual_voltage_reached")
        self.assertGreaterEqual(self.hass.off_calls, 1)

    async def test_persistent_manual_off_exact_current_is_owned_and_cleared_after_off(self):
        manager = self._manager()
        manager.request = ManualChargeRequest(14.7, 2.0)
        manager.state = ManualSessionState.ACTIVE
        manager.started_at = time.time()
        manager._previous_voltage_v = 14.2
        manager._previous_current_a = 0.8
        self.hass.live["switch"] = "on"
        self.hass.live["current"] = 1.2
        self.app.manual_off_current = 1.0
        self.app.manual_off_current_ge = 1.0

        await manager.observe_once()
        self.assertEqual(manager.state, ManualSessionState.STOPPED)
        self.assertEqual(manager.stop_reason, "manual_off_current_reached")
        self.assertEqual(self.manual_off_clear_calls, 1)
        self.assertIsNone(self.app.manual_off_current)
        self.assertIsNone(self.app.manual_off_current_ge)

    async def test_reached_manual_off_is_not_cleared_until_off_is_confirmed(self):
        manager = self._manager()
        manager.request = ManualChargeRequest(14.7, 2.0)
        manager.state = ManualSessionState.ACTIVE
        manager.started_at = time.time()
        manager._previous_current_a = 0.8
        self.hass.live["switch"] = "on"
        self.hass.live["current"] = 1.2
        self.hass.off_result = False
        self.app.manual_off_current = 1.0
        self.app.manual_off_current_ge = 1.0

        await manager.observe_once()

        self.assertEqual(manager.state, ManualSessionState.ARMING)
        self.assertEqual(self.manual_off_clear_calls, 0)
        self.assertEqual(self.app.manual_off_current, 1.0)
        self.assertEqual(self.app.manual_off_current_ge, 1.0)

    async def test_output_off_without_stop_reason_cannot_leave_manual_active(self):
        manager = self._manager()
        manager.request = ManualChargeRequest(14.7, 2.0)
        manager.state = ManualSessionState.ACTIVE
        manager.started_at = time.time()
        self.hass.live["switch"] = "off"

        await manager.observe_once()
        self.assertEqual(manager.state, ManualSessionState.FAILED)
        self.assertEqual(manager.stop_reason, "manual_output_off_unexpected")

    def test_reach_target_survives_restart_as_interrupted_metadata(self):
        manager = self._manager()
        manager.request = ManualChargeRequest(16.5, 1.5)
        manager.reach_current_a = 1.0
        manager.state = ManualSessionState.ACTIVE
        manager.started_at = 100.0
        manager._persist()

        restored = ProductionManualSessionManager(self.app, session_file=self.session_file)
        self.assertEqual(restored.state, ManualSessionState.INTERRUPTED)
        self.assertAlmostEqual(restored.reach_current_a or 0.0, 1.0)


if __name__ == "__main__":
    unittest.main()
