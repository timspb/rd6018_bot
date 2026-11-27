"""Fake-only contracts for the Manual cooling application use case."""

import ast
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import manual_mode
from application import manual_cooling_use_case
from manual_mode import ManualChargeRequest, ManualSessionManager, ManualSessionState


class FakeExecutionPort:
    def __init__(self):
        self.enable_result = SimpleNamespace(verified=True, reason="")
        self.disable_result = SimpleNamespace(verified=True, reason="")
        self.enable_calls = []
        self.disable_calls = []

    async def enable(self, intent, **kwargs):
        self.enable_calls.append((intent, kwargs))
        return self.enable_result

    async def disable(self, intent, **kwargs):
        self.disable_calls.append((intent, kwargs))
        return self.disable_result


class ManualCoolingUseCaseTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.session_file = Path(self.temp_dir.name) / "manual.json"
        self.port = FakeExecutionPort()
        self.factory_patch = mock.patch.object(
            manual_mode, "get_or_create_execution_port", return_value=self.port
        )
        self.factory_patch.start()
        self.addCleanup(self.factory_patch.stop)
        self.manager = ManualSessionManager(
            SimpleNamespace(charge_controller=SimpleNamespace(is_active=False)),
            session_file=str(self.session_file),
        )

    @staticmethod
    def request():
        return ManualChargeRequest(14.4, 5.0, battery_id="fake-battery")

    def saved_state(self):
        return json.loads(self.session_file.read_text(encoding="utf-8"))["state"]

    async def test_duplicate_cooling_skips_execution_and_persistence(self):
        self.manager.state = ManualSessionState.COOLING
        with mock.patch.object(self.manager, "_persist") as persist:
            await self.manager._enter_cooling()
        self.assertEqual(self.port.disable_calls, [])
        persist.assert_not_called()

    async def test_denied_off_transitions_failed_and_persists(self):
        self.port.disable_result = SimpleNamespace(verified=False, reason="denied")
        await self.manager._enter_cooling()
        self.assertEqual(self.port.disable_calls[0][0].requested_mode, "MANUAL_COOLING_STOP")
        self.assertEqual(self.manager.state, ManualSessionState.FAILED)
        self.assertEqual(self.manager.stop_reason, "cooling_output_off_unconfirmed")
        self.assertEqual(self.saved_state(), "failed")

    async def test_verified_off_transitions_to_cooling_and_persists(self):
        with mock.patch.object(manual_cooling_use_case.time, "time", return_value=123.0):
            await self.manager._enter_cooling()
        self.assertEqual(self.port.disable_calls[0][0].requested_mode, "MANUAL_COOLING_STOP")
        self.assertEqual(self.manager.state, ManualSessionState.COOLING)
        self.assertEqual(self.manager.cooling_started_at, 123.0)
        self.assertEqual(self.saved_state(), "cooling")

    async def test_resume_without_request_does_not_enable(self):
        self.manager.state = ManualSessionState.COOLING
        self.manager.request = None
        await self.manager._resume_after_cooling()
        self.assertEqual(self.port.enable_calls, [])
        self.assertEqual(self.manager.state, ManualSessionState.COOLING)

    async def test_verified_resume_uses_canonical_ceiling_updates_pause_and_resets_delta(self):
        self.manager.state = ManualSessionState.COOLING
        self.manager.request = self.request()
        self.manager.cooling_started_at = 90.0
        self.manager.paused_total_s = 4.0
        self.manager._vmax = 15.1
        self.manager._imin = 0.4
        self.manager._delta_confirmations = 2
        self.manager.finish_hold_started_at = 2.0
        with mock.patch.object(manual_cooling_use_case.time, "time", return_value=100.0):
            await self.manager._resume_after_cooling()
        intent, kwargs = self.port.enable_calls[0]
        self.assertEqual(intent.requested_mode, "MANUAL_RESUME")
        self.assertEqual((intent.requested_voltage_v, intent.requested_current_a), (14.4, 5.0))
        self.assertEqual(kwargs["recipe_voltage_ceiling_v"], float(manual_mode.MAX_MANUAL_VOLTAGE))
        self.assertEqual(self.manager.paused_total_s, 14.0)
        self.assertIsNone(self.manager.cooling_started_at)
        self.assertEqual(self.manager.state, ManualSessionState.ACTIVE)
        self.assertIsNone(self.manager._vmax)
        self.assertIsNone(self.manager._imin)
        self.assertEqual(self.manager._delta_confirmations, 0)
        self.assertIsNone(self.manager.finish_hold_started_at)
        self.assertEqual(self.saved_state(), "active")

    async def test_denied_resume_transitions_failed_and_never_active(self):
        self.manager.state = ManualSessionState.COOLING
        self.manager.request = self.request()
        self.port.enable_result = SimpleNamespace(verified=False, reason="resume_denied")
        await self.manager._resume_after_cooling()
        self.assertEqual(self.manager.state, ManualSessionState.FAILED)
        self.assertNotEqual(self.manager.state, ManualSessionState.ACTIVE)
        self.assertEqual(self.manager.stop_reason, "resume_denied")
        self.assertEqual(self.saved_state(), "failed")

    def test_delegates_and_application_import_boundary(self):
        source = Path(manual_mode.__file__).read_text(encoding="utf-8")
        module = ast.parse(source)
        manager = next(
            node for node in module.body
            if isinstance(node, ast.ClassDef) and node.name == "ManualSessionManager"
        )
        methods = {node.name: node for node in manager.body if isinstance(node, ast.AsyncFunctionDef)}
        for method_name, function_name in (
            ("_enter_cooling", "enter_manual_cooling"),
            ("_resume_after_cooling", "resume_manual_after_cooling"),
        ):
            method = methods[method_name]
            self.assertEqual(len(method.body), 1)
            expression = method.body[0].value
            self.assertIsInstance(expression, ast.Await)
            call = expression.value
            self.assertIsInstance(call, ast.Call)
            self.assertEqual(call.func.id, function_name)
        application_source = Path(manual_cooling_use_case.__file__).read_text(encoding="utf-8")
        application_ast = ast.parse(application_source)
        imported = [
            alias.name
            for node in ast.walk(application_ast)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        ]
        self.assertNotIn("manual_mode", imported)
        self.assertNotIn("runtime.production_runtime", imported)


if __name__ == "__main__":
    unittest.main()
