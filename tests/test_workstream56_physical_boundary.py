import unittest

from application.execution_intent import ExecutionIntent, SafetyContext
from application.physical_boundary import PhysicalExecutionBoundary, PhysicalExecutionRequest, PhysicalExecutionResult, PhysicalExecutionStatus
from application.safety import SafetyContext as DomainSafetyContext, SafetyDecision, SafetyState


def intent():
    return ExecutionIntent(14.5, 3.0, "SETPOINT", "decision-1", SafetyContext(telemetry_state="FRESH", containment_state="NORMAL"))


class PhysicalBoundaryTests(unittest.TestCase):
    def test_approved_intent_becomes_request(self):
        decision = SafetyDecision(SafetyState.ALLOW, "ok", (), "HIGH", 1.0)
        request = PhysicalExecutionBoundary().request(intent(), decision, timestamp=2.0)
        self.assertIsInstance(request, PhysicalExecutionRequest)
        self.assertEqual(request.intent_id, "decision-1")
        self.assertFalse(hasattr(request, "transport"))

    def test_denied_intent_is_rejected(self):
        result = PhysicalExecutionBoundary().request(intent(), SafetyDecision(SafetyState.DENY, "OVP", ("OVP",), "HIGH", 1.0), timestamp=2.0)
        self.assertIsInstance(result, PhysicalExecutionResult)
        self.assertEqual(result.status, PhysicalExecutionStatus.REJECTED)
        self.assertTrue(result.rejected)

    def test_result_flags_validate_ack_sequence(self):
        result = PhysicalExecutionResult(PhysicalExecutionStatus.MISMATCH, True, False, True, False, True, "readback mismatch")
        self.assertTrue(result.applied)
        self.assertTrue(result.mismatch)
        with self.assertRaises(ValueError):
            PhysicalExecutionResult(PhysicalExecutionStatus.VERIFIED, True, False, False, True, False, "invalid")

    def test_no_physical_dependencies(self):
        import application.physical_boundary.mapper as module
        with open(module.__file__, encoding="utf-8") as handle:
            source = handle.read()
        for forbidden in ("HA", "ESPHome", "Modbus", "RD6018", "send(", "turn_on", "turn_off"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
