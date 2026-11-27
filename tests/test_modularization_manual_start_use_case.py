"""Fake-only tests for the extracted Manual start application use case."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import manual_mode
from application.manual_start_use_case import start_manual_session
from manual_mode import ManualChargeRequest, ManualSessionManager, ManualSessionState


class ManualStartUseCaseTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.path = Path(self.temp_dir.name) / "manual_session_v2.json"
        self.app = SimpleNamespace(charge_controller=SimpleNamespace(is_active=False))
        self.port = mock.AsyncMock()
        self.port.enable.return_value = SimpleNamespace(verified=True, reason="")
        with mock.patch.object(manual_mode, "get_or_create_execution_port", return_value=self.port):
            self.session = ManualSessionManager(self.app, session_file=str(self.path))

    @staticmethod
    def request():
        return ManualChargeRequest(14.4, 5.0, battery_id="fake-battery")

    async def run_without_background_task(self, request):
        def consume(coro, **kwargs):
            coro.close()
            return SimpleNamespace(name=kwargs.get("name"))

        with mock.patch.object(manual_mode.asyncio, "create_task", side_effect=consume):
            return await start_manual_session(
                self.session, request, max_manual_voltage=16.5
            )

    async def test_active_and_auto_active_rejected_before_request_mutation_or_enable(self):
        original = self.request()
        self.session.state = ManualSessionState.ACTIVE
        with self.assertRaisesRegex(RuntimeError, "already active"):
            await start_manual_session(self.session, original, max_manual_voltage=16.5)
        self.assertIsNone(self.session.request)
        self.port.enable.assert_not_awaited()

        self.session.state = ManualSessionState.IDLE
        self.app.charge_controller.is_active = True
        with self.assertRaisesRegex(RuntimeError, "automatic charge controller"):
            await start_manual_session(self.session, original, max_manual_voltage=16.5)
        self.assertIsNone(self.session.request)
        self.port.enable.assert_not_awaited()

    async def test_arming_is_persisted_before_enable_then_active_event_and_named_task(self):
        observed = {}

        async def enable(intent, **kwargs):
            observed["state"] = self.session.state
            observed["stored"] = json.loads(self.path.read_text(encoding="utf-8"))["state"]
            observed["intent"] = intent
            observed["kwargs"] = kwargs
            return SimpleNamespace(verified=True, reason="")

        self.port.enable.side_effect = enable
        result = await self.run_without_background_task(self.request())
        self.assertTrue(result)
        self.assertEqual(observed["state"], ManualSessionState.ARMING)
        self.assertEqual(observed["stored"], "arming")
        self.assertEqual(observed["intent"].requested_mode, "MANUAL_START")
        self.assertEqual(observed["intent"].safety_context.telemetry_state, "FRESH")
        self.assertEqual(observed["kwargs"]["recipe_voltage_ceiling_v"], 16.5)
        self.assertEqual(self.session.state, ManualSessionState.ACTIVE)
        self.assertEqual(json.loads(self.path.read_text())["state"], "active")
        self.assertTrue(self.session._manual_start_event_emitted)
        self.assertIsNotNone(self.session._task)
        self.assertEqual(self.session._task.name, "rd6018-manual-session")

    async def test_denied_enable_persists_failed_without_start_event(self):
        self.port.enable.return_value = SimpleNamespace(verified=False, reason="fake_denied")
        result = await self.run_without_background_task(self.request())
        self.assertFalse(result)
        self.assertEqual(self.session.state, ManualSessionState.FAILED)
        self.assertEqual(self.session.stop_reason, "fake_denied")
        self.assertEqual(json.loads(self.path.read_text())["state"], "failed")
        self.assertFalse(self.session._manual_start_event_emitted)
        self.assertIsNone(self.session._task)

    async def test_interrupted_restore_never_enables_output(self):
        document = {
            "version": 2, "state": "active", "request": {
                "voltage_v": 14.4, "current_a": 5.0, "stop": {},
                "battery_id": "fake-battery", "capacity_ah": None, "notes": "",
                "profile": None, "stage": "main",
            }, "started_at": 1.0, "paused_total_s": 0.0,
            "cooling_started_at": None, "stop_reason": "",
            "phase_transition_reason": "", "finish_hold_started_at": None,
            "session_identity": None,
        }
        self.path.write_text(json.dumps(document), encoding="utf-8")
        with mock.patch.object(manual_mode, "get_or_create_execution_port", return_value=self.port):
            restored = ManualSessionManager(self.app, session_file=str(self.path))
        self.assertEqual(restored.state, ManualSessionState.INTERRUPTED)
        self.port.enable.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
