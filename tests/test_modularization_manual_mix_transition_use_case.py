"""Fake-only contracts for the extracted Manual MAIN to MIX use case."""

import ast
import inspect
import textwrap
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import manual_mode
from application.manual_mix_transition_use_case import advance_manual_profile_to_mix
from manual_mode import ManualChargeRequest, ManualSessionManager, ManualSessionState
from runtime.charge.profiles.manual import ManualChargeProfile, ManualStageProfile
from v3_core.canonical_events import EventType


class RecordingBoundary:
    def __init__(self, manager, result=True):
        self.manager = manager
        self.result = result
        self.calls = []

    async def apply(self, decision, *, identity):
        self.calls.append((decision, identity, self.manager.request))
        return self.result


class ManualMixTransitionUseCaseTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.app = SimpleNamespace(charge_controller=SimpleNamespace(is_active=False))
        self.port = SimpleNamespace()
        self.factory_patch = mock.patch.object(
            manual_mode, "get_or_create_execution_port", return_value=self.port
        )
        self.factory_patch.start()
        self.addCleanup(self.factory_patch.stop)
        self.manager = ManualSessionManager(
            self.app, session_file=str(Path(self.temp_dir.name) / "session.json")
        )
        self.profile = ManualChargeProfile(
            main=ManualStageProfile(14.4, 5.0, 0.0),
            mix=ManualStageProfile(15.37, 2.63, 0.0),
        )
        self.manager.request = ManualChargeRequest(
            14.4, 5.0, battery_id="battery-x", capacity_ah=72.5,
            notes="keep these notes", profile=self.profile,
        )

    def provide_authority(self):
        self.manager.phase_lifecycle.last_decision = SimpleNamespace(decision_id="decision-x")
        identity = self.manager.identity_integration.create_for_start(
            profile="battery-x", created_at=1.0
        )
        return identity

    async def test_missing_decision_or_identity_has_zero_writes_and_no_mutation(self):
        original = self.manager.request
        boundary = RecordingBoundary(self.manager)
        self.manager.execution_boundary = boundary
        await advance_manual_profile_to_mix(self.manager)
        self.assertEqual(boundary.calls, [])
        self.assertIs(self.manager.request, original)

        self.manager.phase_lifecycle.last_decision = SimpleNamespace(decision_id="decision-x")
        await self.manager._advance_profile_to_mix()
        self.assertEqual(boundary.calls, [])
        self.assertIs(self.manager.request, original)

    async def test_failed_apply_stops_through_existing_route_without_stage_update(self):
        self.provide_authority()
        boundary = RecordingBoundary(self.manager, result=False)
        self.manager.execution_boundary = boundary
        self.manager.state = ManualSessionState.ACTIVE
        self.port.disable = mock.AsyncMock(return_value=SimpleNamespace(verified=True, reason=""))
        original = self.manager.request
        await advance_manual_profile_to_mix(self.manager)
        self.port.disable.assert_awaited_once()
        self.assertEqual(self.manager.stop_reason, "manual_main_to_mix_update_failed")
        self.assertEqual(boundary.calls[0][2], original)
        self.assertIs(self.manager.request, original)
        self.assertEqual(self.manager.request.stage, "main")
        self.assertEqual(self.manager.state, ManualSessionState.STOPPED)

    async def test_success_applies_before_mutation_and_persists_canonical_event(self):
        identity = self.provide_authority()
        self.manager._manual_start_event_emitted = True
        self.manager.stop_reason = "old reason"
        boundary = RecordingBoundary(self.manager)
        self.manager.execution_boundary = boundary
        order = []
        original_persist = self.manager._persist

        def persist():
            order.append(("persist", self.manager.request.stage))
            original_persist()

        self.manager._persist = persist
        with mock.patch.object(
            self.manager.identity_integration, "emit",
            side_effect=lambda **kwargs: order.append(("event", kwargs)),
        ):
            await advance_manual_profile_to_mix(self.manager)

        self.assertEqual(len(boundary.calls), 1)
        self.assertIs(boundary.calls[0][1], identity)
        self.assertIs(boundary.calls[0][2].profile, self.profile)
        self.assertEqual(self.manager.request.stage, "mix")
        self.assertEqual(self.manager.request.voltage_v, self.profile.mix.voltage_v)
        self.assertEqual(self.manager.request.current_a, self.profile.mix.current_a)
        self.assertEqual(self.manager.request.battery_id, "battery-x")
        self.assertEqual(self.manager.request.capacity_ah, 72.5)
        self.assertEqual(self.manager.request.notes, "keep these notes")
        self.assertIs(self.manager.request.profile, self.profile)
        self.assertEqual(self.manager.stop_reason, "")
        self.assertEqual(self.manager.phase_transition_reason, "manual_main_to_mix")
        self.assertEqual(order[0], ("event", {
            "event_type": EventType.PHASE_TRANSITION,
            "phase_before": "main",
            "phase_after": "mix",
            "reason": "manual_main_to_mix",
        }))
        self.assertEqual(order[1], ("persist", "mix"))

    async def test_success_without_start_event_does_not_emit_phase_event(self):
        self.provide_authority()
        self.manager.execution_boundary = RecordingBoundary(self.manager)
        with mock.patch.object(self.manager.identity_integration, "emit") as emit:
            await self.manager._advance_profile_to_mix()
        emit.assert_not_called()
        self.assertEqual(self.manager.request.stage, "mix")

    def test_import_boundary_and_thin_manager_delegate(self):
        source = Path(inspect.getsourcefile(advance_manual_profile_to_mix)).read_text()
        module = ast.parse(source)
        imports = [node for node in ast.walk(module) if isinstance(node, (ast.Import, ast.ImportFrom))]
        imported = [
            alias.name if isinstance(node, ast.Import) else (node.module or "")
            for node in imports for alias in node.names
        ]
        self.assertFalse(any(name == "manual_mode" or name == "runtime.production_runtime" for name in imported))
        method = ast.parse(textwrap.dedent(inspect.getsource(ManualSessionManager._advance_profile_to_mix)))
        calls = [node for node in ast.walk(method) if isinstance(node, ast.Call)]
        self.assertEqual(len(calls), 1)
        self.assertEqual(ast.unparse(calls[0]), "advance_manual_profile_to_mix(self)")


if __name__ == "__main__":
    unittest.main()
