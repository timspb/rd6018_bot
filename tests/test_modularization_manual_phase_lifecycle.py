"""Behavioral parity contract for the Manual MAIN→MIX strategy owner."""

import asyncio
import unittest
from uuid import UUID
from types import SimpleNamespace

from application.manual_execution_boundary import ManualExecutionBoundary
from runtime.charge.strategy.manual_phase_lifecycle import ManualPhaseLifecycle


def profile(*, minimum_current_a=2.3):
    return SimpleNamespace(
        main=SimpleNamespace(
            voltage_v=14.1,
            minimum_current_a=minimum_current_a,
            hold_hours=0.01,
            confirmation_count=2,
            confirmation_interval_seconds=36.0,
        ),
        mix=SimpleNamespace(voltage_v=15.1, current_a=0.9),
    )


class ManualPhaseLifecycleContractTests(unittest.TestCase):
    def test_non_cv_voltage_gate_missing_minimum_and_high_current_are_ineligible(self):
        for candidate_profile, voltage, current, is_cv in (
            (profile(), 14.1, 2.3, False),
            (profile(), 13.89, 2.3, True),
            (profile(minimum_current_a=None), 14.1, 2.3, True),
            (profile(), 14.1, 2.31, True),
        ):
            with self.subTest(profile=candidate_profile, voltage=voltage, current=current, is_cv=is_cv):
                lifecycle = ManualPhaseLifecycle()
                self.assertIsNone(
                    lifecycle.evaluate_main(
                        profile=candidate_profile,
                        voltage_v=voltage,
                        current_a=current,
                        is_cv=is_cv,
                        now=100.0,
                    )
                )
                self.assertEqual(lifecycle.confirmations, 0)
                self.assertIsNone(lifecycle.hold_started_at)
                self.assertEqual(lifecycle.last_confirmation_at, 0.0)
                self.assertIsNone(lifecycle.last_decision)

    def test_near_target_margin_boundary_is_inclusive(self):
        candidate_profile = profile()
        at_boundary = ManualPhaseLifecycle()
        self.assertIsNone(
            at_boundary.evaluate_main(
                profile=candidate_profile,
                voltage_v=13.90,
                current_a=2.3,
                is_cv=True,
                now=100.0,
            )
        )
        self.assertEqual(at_boundary.confirmations, 1)
        self.assertEqual(at_boundary.last_confirmation_at, 100.0)

        below_boundary = ManualPhaseLifecycle()
        below_boundary.evaluate_main(
            profile=candidate_profile,
            voltage_v=13.89,
            current_a=2.3,
            is_cv=True,
            now=100.0,
        )
        self.assertEqual(below_boundary.confirmations, 0)

    def test_confirmation_interval_and_hold_exact_boundaries(self):
        candidate_profile = profile()
        lifecycle = ManualPhaseLifecycle()
        evidence = dict(profile=candidate_profile, voltage_v=14.1, current_a=2.3, is_cv=True)

        self.assertIsNone(lifecycle.evaluate_main(**evidence, now=74.0))
        self.assertEqual(lifecycle.confirmations, 1)
        self.assertIsNone(lifecycle.evaluate_main(**evidence, now=109.999))
        self.assertEqual(lifecycle.confirmations, 1)
        self.assertIsNone(lifecycle.evaluate_main(**evidence, now=110.0))
        self.assertEqual(lifecycle.confirmations, 2)
        self.assertEqual(lifecycle.hold_started_at, 110.0)

        self.assertIsNone(lifecycle.evaluate_main(**evidence, now=145.999))
        decision = lifecycle.evaluate_main(**evidence, now=146.0)
        self.assertIsNotNone(decision)
        self.assertEqual(lifecycle.confirmations, 3)

        self.assertEqual(decision.phase_before, "main")
        self.assertEqual(decision.phase_after, "mix")
        self.assertEqual(decision.voltage_v, 15.1)
        self.assertEqual(decision.current_a, 0.9)
        self.assertEqual(decision.reason, "MAIN minimum-current hold completed")
        self.assertEqual(decision.timestamp, 146.0)
        self.assertTrue(decision.decision_id)
        self.assertEqual(UUID(decision.decision_id).hex, decision.decision_id)
        intent = decision.execution_intent
        self.assertEqual(intent.requested_mode, "MANUAL_MIX_SETPOINT")
        self.assertEqual(intent.source_decision_id, decision.decision_id)
        self.assertEqual(intent.requested_voltage_v, 15.1)
        self.assertEqual(intent.requested_current_a, 0.9)
        self.assertEqual(intent.safety_context.telemetry_state, "FRESH")
        self.assertEqual(intent.safety_context.lease_state, "V2_PHYSICAL_OWNER")
        self.assertEqual(intent.safety_context.containment_state, "NORMAL")
        self.assertEqual(intent.safety_context.verification_state, "REQUIRED")
        self.assertEqual(intent.safety_context.limits_reference, "existing V2 guarded setter policy")

        other = ManualPhaseLifecycle()
        for timestamp in (74.0, 110.0):
            other.evaluate_main(**evidence, now=timestamp)
        other_decision = other.evaluate_main(**evidence, now=146.0)
        self.assertNotEqual(decision.decision_id, other_decision.decision_id)

    def test_reset_and_new_lifecycle_start_clean(self):
        lifecycle = ManualPhaseLifecycle()
        evidence = dict(profile=profile(), voltage_v=14.1, current_a=2.3, is_cv=True)
        lifecycle.evaluate_main(**evidence, now=0.0)
        lifecycle.evaluate_main(**evidence, now=36.0)
        lifecycle.evaluate_main(**evidence, now=72.0)
        self.assertIsNotNone(lifecycle.last_decision)

        lifecycle.reset()
        self.assertEqual(lifecycle.confirmations, 0)
        self.assertIsNone(lifecycle.hold_started_at)
        self.assertEqual(lifecycle.last_confirmation_at, 0.0)
        self.assertIsNone(lifecycle.last_decision)

        fresh = ManualPhaseLifecycle()
        self.assertEqual(fresh.confirmations, 0)
        self.assertIsNone(fresh.hold_started_at)
        self.assertEqual(fresh.last_confirmation_at, 0.0)
        self.assertIsNone(fresh.last_decision)

    def test_execution_boundary_forwards_identity_and_rejects_missing_identity(self):
        class RecordingPort:
            def __init__(self):
                self.calls = []

            async def apply_intent(self, intent, *, identity):
                self.calls.append((intent, identity))
                return SimpleNamespace(verified=True)

        lifecycle = ManualPhaseLifecycle()
        evidence = dict(profile=profile(), voltage_v=14.1, current_a=2.3, is_cv=True)
        lifecycle.evaluate_main(**evidence, now=74.0)
        lifecycle.evaluate_main(**evidence, now=110.0)
        decision = lifecycle.evaluate_main(**evidence, now=146.0)
        port = RecordingPort()
        boundary = ManualExecutionBoundary.__new__(ManualExecutionBoundary)
        boundary.execution_port = port
        identity = SimpleNamespace(session_id="session-1", trace_id="trace-1")

        self.assertFalse(asyncio.run(boundary.apply(decision, identity=None)))
        self.assertEqual(port.calls, [])
        self.assertTrue(asyncio.run(boundary.apply(decision, identity=identity)))
        self.assertEqual(port.calls, [(decision.execution_intent, identity)])


if __name__ == "__main__":
    unittest.main()
