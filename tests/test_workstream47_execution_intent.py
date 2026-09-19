import unittest

from application.charge_engine import BatteryState, ChargeEngine, Phase, TelemetrySnapshot
from application.charge_program import BatteryProfile, resolve_charge_program
from application.execution_intent import (
    DecisionIntentMapper,
    ExecutionSafetyPolicy,
    SafetyContext,
    SafetyOutcome,
)


class ExecutionIntentBoundaryTests(unittest.TestCase):
    def setUp(self):
        program = resolve_charge_program(BatteryProfile("battery", "EFB", 72), "AUTO")
        self.decision = ChargeEngine(program).evaluate(
            BatteryState(phase=Phase.MAIN),
            TelemetrySnapshot(1.0, 14.8, 2.0, 23.0),
        )
        self.context = SafetyContext(
            telemetry_state="FRESH",
            lease_state="OBSERVED",
            containment_state="NORMAL",
            verification_state="READY",
            limits_reference="test-policy",
        )

    def test_decision_to_intent(self):
        result = DecisionIntentMapper.from_decision(
            self.decision,
            self.context,
            ExecutionSafetyPolicy(max_voltage_v=16.5, max_current_a=12.0),
        )
        self.assertEqual(result.outcome, SafetyOutcome.ALLOWED)
        self.assertEqual(result.intent.source_decision_id, self.decision.decision_id)
        self.assertEqual(result.intent.requested_voltage_v, self.decision.desired_voltage_v)

    def test_safety_allows_and_limits(self):
        result = DecisionIntentMapper.from_decision(
            self.decision,
            self.context,
            ExecutionSafetyPolicy(max_voltage_v=14.0, max_current_a=1.0),
        )
        self.assertEqual(result.outcome, SafetyOutcome.LIMITED)
        self.assertEqual(result.intent.requested_voltage_v, 14.0)
        self.assertEqual(result.intent.requested_current_a, 1.0)

    def test_safety_rejects_bad_context(self):
        context = SafetyContext(telemetry_state="STALE", containment_state="CONTAINMENT")
        result = DecisionIntentMapper.from_decision(
            self.decision,
            context,
            ExecutionSafetyPolicy(max_voltage_v=16.5, max_current_a=12.0),
        )
        self.assertEqual(result.outcome, SafetyOutcome.DENIED)
        self.assertIsNone(result.intent)

    def test_conversion_is_deterministic(self):
        policy = ExecutionSafetyPolicy(max_voltage_v=16.5, max_current_a=12.0)
        first = DecisionIntentMapper.from_decision(self.decision, self.context, policy)
        second = DecisionIntentMapper.from_decision(self.decision, self.context, policy)
        self.assertEqual(first, second)

    def test_missing_program_or_setpoints_is_rejected(self):
        program = resolve_charge_program(BatteryProfile("battery", "AGM", 72), "AUTO")
        decision = ChargeEngine(program).evaluate(
            BatteryState(phase=Phase.MAIN),
            TelemetrySnapshot(1.0, None, 2.0, 23.0, fresh=False),
        )
        result = DecisionIntentMapper.from_decision(
            decision,
            self.context,
            ExecutionSafetyPolicy(max_voltage_v=16.5, max_current_a=12.0),
        )
        self.assertEqual(result.outcome, SafetyOutcome.DENIED)

    def test_intent_layer_has_no_physical_dependencies(self):
        import application.execution_intent.mapper as mapper
        import application.execution_intent.policy as policy

        for module in (mapper, policy):
            with open(module.__file__, encoding="utf-8") as handle:
                source = handle.read()
            for forbidden in ("hass_api", "ESPHome", "Modbus", "turn_on", "turn_off", "ChargeControllerV2"):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
