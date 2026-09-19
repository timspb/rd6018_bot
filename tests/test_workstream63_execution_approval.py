import unittest

from application.execution_intent import ExecutionIntent, SafetyContext
from application.physical_boundary import (
    ApprovalStatus,
    ExecutionApproval,
    ExecutionApprovalGate,
    ExecutionMode,
)
from application.safety import SafetyDecision, SafetyState


EVIDENCE = (
    ("current_state", "MAIN"),
    ("telemetry_freshness", "FRESH"),
    ("safety_status", "ALLOW"),
    ("program_identity", "auto:calcium:test"),
    ("lifecycle_state", "ACTIVE"),
)


def intent():
    return ExecutionIntent(
        14.4,
        5.0,
        "SETPOINT",
        "decision-63",
        SafetyContext(telemetry_state="FRESH", lease_state="OBSERVE"),
    )


def approval(state=SafetyState.ALLOW, *, expiry=100.0, evidence=EVIDENCE):
    return ExecutionApproval(
        decision_id="decision-63",
        intent_id="decision-63",
        safety_decision=SafetyDecision(state, state.value, (), "HIGH", 1.0),
        evidence=evidence,
        approved_by="synthetic-operator",
        timestamp=10.0,
        expiry=expiry,
    )


class ExecutionApprovalGateTests(unittest.TestCase):
    def setUp(self):
        self.gate = ExecutionApprovalGate()

    def test_approved_real_mode_creates_only_contract_request(self):
        result = self.gate.evaluate(
            intent(), approval(), now=20.0, mode=ExecutionMode.REAL_EXECUTION
        )
        self.assertEqual(result.status, ApprovalStatus.APPROVED)
        self.assertIsNotNone(result.request)
        self.assertEqual(result.request.intent_id, "decision-63")

    def test_missing_approval_rejects(self):
        result = self.gate.evaluate(
            intent(), None, now=20.0, mode=ExecutionMode.REAL_EXECUTION
        )
        self.assertEqual(result.status, ApprovalStatus.REJECTED)
        self.assertIsNone(result.request)

    def test_expired_approval_rejects(self):
        result = self.gate.evaluate(
            intent(), approval(expiry=20.0), now=20.0, mode=ExecutionMode.REAL_EXECUTION
        )
        self.assertEqual(result.status, ApprovalStatus.EXPIRED)
        self.assertIsNone(result.request)

    def test_missing_evidence_is_rejected_at_contract_creation(self):
        with self.assertRaises(ValueError):
            approval(evidence=(("current_state", "MAIN"),))

    def test_denied_safety_cannot_pass_gate(self):
        result = self.gate.evaluate(
            intent(), approval(SafetyState.DENY), now=20.0, mode=ExecutionMode.REAL_EXECUTION
        )
        self.assertEqual(result.status, ApprovalStatus.REJECTED)
        self.assertIsNone(result.request)

    def test_simulation_validates_but_never_creates_physical_request(self):
        result = self.gate.evaluate(
            intent(), approval(), now=20.0, mode=ExecutionMode.SIMULATION
        )
        self.assertEqual(result.status, ApprovalStatus.APPROVED)
        self.assertIsNone(result.request)
        self.assertIn("suppressed", result.reason)

    def test_identity_mismatch_is_rejected(self):
        mismatched = ExecutionApproval(
            "other-decision", "other-decision", approval().safety_decision,
            EVIDENCE, "synthetic-operator", 10.0, 100.0
        )
        result = self.gate.evaluate(
            intent(), mismatched, now=20.0, mode=ExecutionMode.REAL_EXECUTION
        )
        self.assertEqual(result.status, ApprovalStatus.REJECTED)
        self.assertIsNone(result.request)


if __name__ == "__main__":
    unittest.main()
