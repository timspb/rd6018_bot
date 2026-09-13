import unittest

from runtime.charge.intent import ChargeIntent
from runtime.output.intent import OutputAction, SafeOutputIntent
from runtime.output.execution_policy import ExecutionPolicy, ExecutionPolicyContext, LegacyExecutionPolicyAdapter
from runtime.safety import SafetyDecision, SafetyEngine, SafetyLimits


class V3ExecutionPolicyTests(unittest.TestCase):
    def setUp(self):
        self.engine = SafetyEngine(SafetyLimits(20.0, 12.0))
        self.policy = ExecutionPolicy()

    def test_enable_requires_fresh_complete_evidence(self):
        intent = SafeOutputIntent(OutputAction.ENABLE, 14.4, 2.0)
        safety = SafetyDecision(True, "ok", intent=ChargeIntent(14.4, 2.0))
        accepted = self.policy.evaluate(intent, safety)
        denied = self.policy.evaluate(intent, safety, ExecutionPolicyContext(telemetry_fresh=False))
        self.assertTrue(accepted.allowed)
        self.assertFalse(denied.allowed)

    def test_denied_safety_blocks_enable(self):
        intent = SafeOutputIntent(OutputAction.ENABLE, 14.4, 2.0)
        safety = SafetyDecision(False, "blocked")
        self.assertFalse(self.policy.evaluate(intent, safety).allowed)

    def test_disable_is_always_allowed(self):
        intent = SafeOutputIntent(OutputAction.DISABLE)
        self.assertTrue(self.policy.evaluate(intent, SafetyDecision(False, "hard stop")).allowed)

    def test_reset_requires_safe_state(self):
        intent = SafeOutputIntent(OutputAction.RESET_PROTECTION, target_ovp=15.0, target_ocp=3.0, source="mix")
        safety = SafetyDecision(True, "ok")
        self.assertFalse(self.policy.evaluate(intent, safety, ExecutionPolicyContext(unsafe_state=True)).allowed)

    def test_legacy_requirements_are_comparable(self):
        intent = SafeOutputIntent(OutputAction.ENABLE, 14.4, 2.0)
        v2 = LegacyExecutionPolicyAdapter.requirements(intent)
        result = LegacyExecutionPolicyAdapter.compare(v2, dict(v2))
        self.assertEqual(result.status, "MATCH")


if __name__ == "__main__":
    unittest.main()
