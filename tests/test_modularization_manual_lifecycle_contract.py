"""Fake-only lifecycle contracts for the base ManualSessionManager."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import manual_mode
from manual_mode import ManualChargeRequest, ManualSessionManager, ManualSessionState
from runtime.charge.profiles.manual import ManualChargeProfile, ManualStageProfile


class FakeExecutionPort:
    """Non-actuating execution port recording calls and manager state at entry."""

    def __init__(self, manager_ref=None):
        self.manager_ref = manager_ref
        self.enable_result = SimpleNamespace(verified=True, reason="")
        self.disable_result = SimpleNamespace(verified=True, reason="")
        self.enable_calls = []
        self.disable_calls = []
        self.emergency_off_calls = []

    async def enable(self, intent, **kwargs):
        state = self.manager_ref.state if self.manager_ref is not None else None
        self.enable_calls.append((intent, kwargs, state))
        return self.enable_result

    async def disable(self, intent, **kwargs):
        state = self.manager_ref.state if self.manager_ref is not None else None
        self.disable_calls.append((intent, kwargs, state))
        return self.disable_result

    async def request_emergency_off(self):
        state = self.manager_ref.state if self.manager_ref is not None else None
        self.emergency_off_calls.append(state)
        return True


class FakeExecutionBoundary:
    def __init__(self, manager_ref, result=True):
        self.manager_ref = manager_ref
        self.result = result
        self.calls = []

    async def apply(self, decision, *, identity):
        self.calls.append((decision, identity, self.manager_ref.request.stage))
        return self.result


class ManualLifecycleContractTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.session_file = Path(self.temp_dir.name) / "manual_session_v2.json"
        self.app = SimpleNamespace(charge_controller=SimpleNamespace(is_active=False))
        self.port = FakeExecutionPort()
        self._factory_patch = mock.patch.object(
            manual_mode, "get_or_create_execution_port", return_value=self.port
        )
        self._factory_patch.start()
        self.addCleanup(self._factory_patch.stop)
        self.manager = ManualSessionManager(self.app, session_file=str(self.session_file))
        self.port.manager_ref = self.manager

    @staticmethod
    def request(*, profile=False):
        staged_profile = None
        if profile:
            staged_profile = ManualChargeProfile(
                main=ManualStageProfile(14.4, 5.0, 0.0),
                mix=ManualStageProfile(15.0, 2.0, 0.0),
            )
        return ManualChargeRequest(
            14.4, 5.0, battery_id="fake-battery", profile=staged_profile
        )

    async def start_without_background_task(self, request):
        def consume(coro, **kwargs):
            coro.close()
            return SimpleNamespace(name=kwargs.get("name"))

        with mock.patch.object(manual_mode.asyncio, "create_task", side_effect=consume):
            return await self.manager.start(request)

    def create_identity(self):
        return self.manager.identity_integration.create_for_start(
            profile="fake-battery", created_at=1.0
        )

    def saved_document(self):
        return json.loads(self.session_file.read_text(encoding="utf-8"))

    async def test_start_rejects_unauthorized_state_before_enable(self):
        self.manager.state = ManualSessionState.ACTIVE
        with self.assertRaisesRegex(RuntimeError, "already active"):
            await self.manager.start(self.request())
        self.assertEqual(self.port.enable_calls, [])
        self.assertEqual(self.manager.state, ManualSessionState.ACTIVE)

        self.manager.state = ManualSessionState.IDLE
        self.app.charge_controller.is_active = True
        with self.assertRaisesRegex(RuntimeError, "automatic charge controller"):
            await self.manager.start(self.request())
        self.assertEqual(self.port.enable_calls, [])
        self.assertEqual(self.manager.state, ManualSessionState.IDLE)

    async def test_start_persists_arming_before_enable_and_active_after_verified_enable(self):
        self.manager._imin = 0.4
        self.manager._vmax = 15.1
        self.manager._delta_confirmations = 2
        self.manager._last_delta_confirmation = 42.0
        self.manager.finish_hold_started_at = 30.0
        result = await self.start_without_background_task(self.request())
        self.assertTrue(result)
        self.assertEqual(len(self.port.enable_calls), 1)
        _, _, state_at_enable = self.port.enable_calls[0]
        self.assertEqual(state_at_enable, ManualSessionState.ARMING)
        self.assertEqual(self.saved_document()["state"], "active")
        self.assertEqual(self.manager.state, ManualSessionState.ACTIVE)
        self.assertIsNone(self.manager._imin)
        self.assertIsNone(self.manager._vmax)
        self.assertEqual(self.manager._delta_confirmations, 0)
        self.assertEqual(self.manager._last_delta_confirmation, 0.0)
        self.assertIsNone(self.manager.finish_hold_started_at)

    async def test_failed_start_enable_does_not_claim_active(self):
        self.port.enable_result = SimpleNamespace(verified=False, reason="fake_denied")
        result = await self.start_without_background_task(self.request())
        self.assertFalse(result)
        self.assertEqual(self.port.enable_calls[0][2], ManualSessionState.ARMING)
        self.assertEqual(self.manager.state, ManualSessionState.FAILED)
        self.assertEqual(self.manager.stop_reason, "fake_denied")
        self.assertEqual(self.saved_document()["state"], "failed")

    async def test_interrupted_constructor_restore_never_auto_enables(self):
        self.session_file.write_text(json.dumps({
            "version": 2,
            "state": "active",
            "request": {
                "voltage_v": 14.4, "current_a": 5.0, "stop": {},
                "battery_id": "fake-battery", "capacity_ah": None,
                "notes": "", "profile": None, "stage": "main",
            },
            "started_at": 123.0,
            "paused_total_s": 0.0,
            "cooling_started_at": None,
            "stop_reason": "",
            "phase_transition_reason": "",
            "finish_hold_started_at": 456.0,
            "session_identity": None,
        }), encoding="utf-8")
        self.port.enable_calls.clear()
        self.manager = ManualSessionManager(self.app, session_file=str(self.session_file))
        self.port.manager_ref = self.manager
        self.assertEqual(self.manager.state, ManualSessionState.INTERRUPTED)
        self.assertEqual(self.manager.finish_hold_started_at, 456.0)
        self.assertIsNotNone(self.manager.request)
        self.assertEqual(self.port.enable_calls, [])
        self.assertEqual(self.saved_document()["state"], "interrupted")
        self.assertEqual(self.saved_document()["finish_hold_started_at"], 456.0)

    async def test_stop_verified_off_then_terminal_state_is_saved(self):
        self.create_identity()
        self.manager.state = ManualSessionState.ACTIVE
        result = await self.manager.stop("fake_operator_stop")
        self.assertTrue(result)
        self.assertEqual(self.manager.state, ManualSessionState.STOPPED)
        self.assertEqual(self.saved_document()["state"], "stopped")
        self.assertEqual(self.port.disable_calls[0][0].requested_mode, "MANUAL_STOP")

    async def test_stop_denied_off_is_failed_and_never_stopped(self):
        self.manager._imin = 0.4
        self.manager._vmax = 15.1
        self.manager._delta_confirmations = 2
        self.manager._last_delta_confirmation = 42.0
        self.manager.finish_hold_started_at = 30.0
        self.port.disable_result = SimpleNamespace(verified=False, reason="fake_off_denied")
        result = await self.manager.stop("fake_operator_stop")
        self.assertFalse(result)
        self.assertEqual(self.manager.state, ManualSessionState.FAILED)
        self.assertNotEqual(self.manager.state, ManualSessionState.STOPPED)
        self.assertEqual(self.saved_document()["state"], "failed")
        self.assertEqual(
            (self.manager._imin, self.manager._vmax, self.manager._delta_confirmations,
             self.manager._last_delta_confirmation, self.manager.finish_hold_started_at),
            (0.4, 15.1, 2, 42.0, 30.0),
        )

    async def test_cooling_off_denial_records_failure_and_base_manager_becomes_failed(self):
        self.manager.state = ManualSessionState.ACTIVE
        self.manager._imin = 0.4
        self.manager._vmax = 15.1
        self.manager._delta_confirmations = 2
        self.manager._last_delta_confirmation = 42.0
        self.manager.finish_hold_started_at = 30.0
        self.port.disable_result = SimpleNamespace(verified=False, reason="fake_off_denied")
        await self.manager._enter_cooling()
        self.assertEqual(self.port.disable_calls[0][0].requested_mode, "MANUAL_COOLING_STOP")
        self.assertEqual(self.manager.state, ManualSessionState.FAILED)
        self.assertEqual(self.manager.stop_reason, "cooling_output_off_unconfirmed")
        self.assertEqual(self.saved_document()["state"], "failed")
        self.assertEqual(self.manager._imin, 0.4)
        self.assertEqual(self.manager._vmax, 15.1)
        self.assertEqual(self.manager._delta_confirmations, 2)
        self.assertEqual(self.manager._last_delta_confirmation, 42.0)
        self.assertEqual(self.manager.finish_hold_started_at, 30.0)

    async def test_verified_cooling_off_transitions_to_cooling(self):
        self.manager.state = ManualSessionState.ACTIVE
        self.manager._imin = 0.4
        self.manager._vmax = 15.1
        self.manager._delta_confirmations = 2
        self.manager._last_delta_confirmation = 42.0
        self.manager.finish_hold_started_at = 30.0
        await self.manager._enter_cooling()
        self.assertEqual(self.manager.state, ManualSessionState.COOLING)
        self.assertEqual(self.saved_document()["state"], "cooling")
        self.assertIsNotNone(self.manager.cooling_started_at)
        self.assertIsNone(self.manager._imin)
        self.assertIsNone(self.manager._vmax)
        self.assertEqual(self.manager._delta_confirmations, 0)
        self.assertEqual(self.manager._last_delta_confirmation, 0.0)
        self.assertIsNone(self.manager.finish_hold_started_at)

    async def test_cooling_resume_verified_enable_restores_active_and_resets_delta(self):
        self.manager.state = ManualSessionState.COOLING
        self.manager.request = self.request()
        self.manager.cooling_started_at = 1.0
        self.manager._vmax = 15.1
        self.manager._imin = 0.4
        self.manager._delta_confirmations = 2
        self.manager.finish_hold_started_at = 2.0
        await self.manager._resume_after_cooling()
        self.assertEqual(self.port.enable_calls[0][2], ManualSessionState.ARMING)
        self.assertEqual(self.port.enable_calls[0][0].requested_mode, "MANUAL_RESUME")
        self.assertEqual(self.manager.state, ManualSessionState.ACTIVE)
        self.assertIsNone(self.manager._vmax)
        self.assertIsNone(self.manager._imin)
        self.assertEqual(self.manager._delta_confirmations, 0)
        self.assertIsNone(self.manager.finish_hold_started_at)
        self.assertEqual(self.saved_document()["state"], "active")

    async def test_cooling_resume_denied_enable_never_claims_active(self):
        self.manager.state = ManualSessionState.COOLING
        self.manager.request = self.request()
        self.port.enable_result = SimpleNamespace(verified=False, reason="fake_resume_denied")
        await self.manager._resume_after_cooling()
        self.assertEqual(self.manager.state, ManualSessionState.FAILED)
        self.assertNotEqual(self.manager.state, ManualSessionState.ACTIVE)
        self.assertEqual(self.manager.stop_reason, "fake_resume_denied")
        self.assertEqual(self.saved_document()["state"], "failed")

    async def test_main_to_mix_missing_decision_or_identity_has_no_write(self):
        self.manager.request = self.request(profile=True)
        await self.manager._advance_profile_to_mix()
        self.assertEqual(self.manager.request.stage, "main")
        self.assertEqual(self.manager.execution_boundary.audit, [])

        self.manager.phase_lifecycle.last_decision = SimpleNamespace(decision_id="fake-decision")
        await self.manager._advance_profile_to_mix()
        self.assertEqual(self.manager.request.stage, "main")
        self.assertEqual(self.manager.execution_boundary.audit, [])

    async def test_main_to_mix_failed_apply_uses_existing_stop(self):
        self.manager.request = self.request(profile=True)
        self.manager.phase_lifecycle.last_decision = SimpleNamespace(decision_id="fake-decision")
        self.create_identity()
        boundary = FakeExecutionBoundary(self.manager, result=False)
        self.manager.execution_boundary = boundary
        await self.manager._advance_profile_to_mix()
        self.assertEqual(boundary.calls[0][2], "main")
        self.assertEqual(len(self.port.disable_calls), 1)
        self.assertEqual(self.port.disable_calls[0][0].requested_mode, "MANUAL_STOP")
        self.assertEqual(self.manager.request.stage, "main")
        self.assertEqual(self.manager.state, ManualSessionState.STOPPED)
        self.assertEqual(self.manager.stop_reason, "manual_main_to_mix_update_failed")

    async def test_main_to_mix_success_updates_request_after_apply(self):
        self.manager.request = self.request(profile=True)
        self.manager.phase_lifecycle.last_decision = SimpleNamespace(decision_id="fake-decision")
        self.create_identity()
        boundary = FakeExecutionBoundary(self.manager, result=True)
        self.manager.execution_boundary = boundary
        await self.manager._advance_profile_to_mix()
        self.assertEqual(boundary.calls[0][2], "main")
        self.assertEqual(self.manager.request.stage, "mix")
        self.assertEqual(self.manager.request.voltage_v, 15.0)
        self.assertEqual(self.manager.request.current_a, 2.0)
        self.assertEqual(self.saved_document()["request"]["stage"], "mix")

    async def test_run_exception_attempts_emergency_off_before_failed_transition(self):
        self.manager.state = ManualSessionState.ACTIVE
        self.manager.observe_once = mock.AsyncMock(side_effect=ValueError("fake observer failure"))
        await self.manager._run()
        self.assertEqual(self.port.disable_calls, [])
        self.assertEqual(self.port.emergency_off_calls, [ManualSessionState.ACTIVE])
        self.assertEqual(self.manager.state, ManualSessionState.FAILED)
        self.assertEqual(self.saved_document()["state"], "failed")


if __name__ == "__main__":
    unittest.main()
