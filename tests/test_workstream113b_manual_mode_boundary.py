import asyncio
import inspect
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from application.manual_execution_boundary import ManualExecutionBoundary
from application.manual_phase_lifecycle import ManualPhaseLifecycle
from runtime.charge.profiles.manual import ManualChargeProfile
from manual_mode import ManualChargeRequest, ManualSessionManager
from rd6018_telemetry import RegulationMode


class ManualModeBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.profile = ManualChargeProfile.from_mapping({
            "main": {"voltage_v": 14.1, "current_a": 5.0, "minimum_current_a": 2.3, "hold_hours": 0.001},
            "mix": {"voltage_v": 15.1, "current_a": 0.9, "delta_voltage_v": 0.001, "delta_current_a": 0.001, "hold_hours": 0.04},
        })

    def test_phase_lifecycle_creates_decision_and_targets(self):
        lifecycle = ManualPhaseLifecycle()
        self.assertIsNone(lifecycle.evaluate_main(profile=self.profile, voltage_v=14.1, current_a=2.3, is_cv=True, now=10.0))
        decision = lifecycle.evaluate_main(profile=self.profile, voltage_v=14.1, current_a=2.3, is_cv=True, now=14.0)
        self.assertIsNotNone(decision)
        self.assertEqual(decision.phase_after, "mix")
        self.assertEqual(decision.voltage_v, 15.1)
        self.assertEqual(decision.current_a, 0.9)
        self.assertEqual(decision.execution_intent.source_decision_id, decision.decision_id)
        self.assertEqual(decision.execution_intent.requested_current_a, 0.9)

    def test_manual_mode_has_no_direct_setter_calls(self):
        source = inspect.getsource(__import__("manual_mode"))
        self.assertNotIn("self.app.hass.set_current", source)
        self.assertNotIn("self.app.hass.set_voltage", source)

    def test_execution_boundary_requires_identity_and_verifies_readback(self):
        class Owner:
            def __init__(self):
                self.live = {"switch": "on", "battery_voltage": 13.0, "_meta": {
                    "set_voltage_readback_v2": {"status": "ok", "age_s": 0.0},
                    "set_current_readback_v2": {"status": "ok", "age_s": 0.0},
                }, "set_voltage_readback_v2": 14.1, "set_current_readback_v2": 5.0}

            async def get_all_live(self): return dict(self.live)
            async def set_current(self, value): self.live["set_current_readback_v2"] = value; return True
            async def set_voltage(self, value): self.live["set_voltage_readback_v2"] = value; return True

        lifecycle = ManualPhaseLifecycle()
        lifecycle.evaluate_main(profile=self.profile, voltage_v=14.1, current_a=2.3, is_cv=True, now=10.0)
        decision = lifecycle.evaluate_main(profile=self.profile, voltage_v=14.1, current_a=2.3, is_cv=True, now=14.0)
        owner = Owner()
        boundary = ManualExecutionBoundary(owner)
        identity = SimpleNamespace(session_id="s1", trace_id="t1")
        self.assertTrue(asyncio.run(boundary.apply(decision, identity=identity)))
        self.assertEqual(boundary.audit[-1].result, "VERIFIED")

    def test_production_manual_manager_routes_profile_phase_through_identity_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            app = SimpleNamespace(hass=None, charge_controller=SimpleNamespace(is_active=False))
            manager = ManualSessionManager(app, session_file=f"{directory}/manual.json")
            manager.request = ManualChargeRequest.from_profile(self.profile, battery_id="bench")
            manager.identity_integration.create_for_start(profile="bench", created_at=1.0)
            manager._manual_start_event_emitted = True
            manager._persist = Mock()
            manager.execution_boundary.apply = AsyncMock(return_value=True)

            now = time.time()
            manager.phase_lifecycle.confirmations = self.profile.main.confirmation_count - 1
            manager.phase_lifecycle.last_confirmation_at = now - self.profile.main.confirmation_interval_seconds - 1
            manager.phase_lifecycle.hold_started_at = now - self.profile.main.hold_hours * 3600 - 1
            with patch("manual_mode.resolve_regulation", return_value=RegulationMode.CV):
                self.assertEqual(
                    manager._main_tail_reason({"battery_voltage": 14.1, "current": 2.3}),
                    "manual_main_to_mix",
                )

            asyncio.run(manager._advance_profile_to_mix())
            manager.execution_boundary.apply.assert_awaited_once_with(
                manager.phase_lifecycle.last_decision,
                identity=manager.identity_integration.identity,
            )
            self.assertEqual(manager.request.stage, "mix")
            self.assertEqual(manager.phase_transition_reason, "manual_main_to_mix")


if __name__ == "__main__":
    unittest.main()
