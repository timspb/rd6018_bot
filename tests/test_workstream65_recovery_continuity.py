import unittest

from application.decision_audit import DecisionAuditEvent, DecisionAuditTrail
from application.execution_intent import ExecutionIntent, SafetyContext
from application.physical_boundary import ExecutionApproval
from application.recovery import (
    AuditContinuityValidator,
    RecoveryKind,
    V3RecoveryCoordinator,
    V3RecoverySnapshot,
)
from application.safety import SafetyDecision, SafetyState


def intent(decision_id="decision-65"):
    return ExecutionIntent(14.4, 5.0, "SETPOINT", decision_id, SafetyContext(telemetry_state="FRESH"))


def approval(decision_id="decision-65", expiry=100.0):
    return ExecutionApproval(
        decision_id, decision_id,
        SafetyDecision(SafetyState.ALLOW, "approved", (), "HIGH", 1.0),
        (("current_state", "MAIN"), ("telemetry_freshness", "FRESH"),
         ("safety_status", "ALLOW"), ("program_identity", "calcium"),
         ("lifecycle_state", "ACTIVE")),
        "synthetic-operator", 10.0, expiry,
    )


def snapshot(*, telemetry_fresh=True, safety=SafetyState.ALLOW, pending=True, approved=True):
    return V3RecoverySnapshot(
        "session-65", "trace-65", "ACTIVE", "auto:calcium", "MAIN",
        telemetry_fresh, safety, intent() if pending else None,
        approval() if approved else None, 1,
    )


class RecoveryContinuityTests(unittest.TestCase):
    def setUp(self):
        self.coordinator = V3RecoveryCoordinator()

    def test_active_charge_recovers_with_valid_approval(self):
        result = self.coordinator.decide(snapshot(), now=20.0)
        self.assertEqual(result.kind, RecoveryKind.RECOVER_EXISTING)
        self.assertTrue(result.execution_allowed)

    def test_hold_recovery_preserves_state_but_requires_fresh_telemetry(self):
        hold = V3RecoverySnapshot(
            "session-65", "trace-65", "HOLD", "manual:Baic72", "HOLD",
            False, SafetyState.ALLOW, intent(), approval(), 4,
        )
        result = self.coordinator.decide(hold, now=20.0)
        self.assertEqual(result.kind, RecoveryKind.RECOVER_EXISTING)
        self.assertFalse(result.execution_allowed)
        self.assertIs(result.snapshot, hold)

    def test_denied_recovery_does_not_resume_execution(self):
        result = self.coordinator.decide(snapshot(safety=SafetyState.DENY), now=20.0)
        self.assertEqual(result.kind, RecoveryKind.RECOVER_EXISTING)
        self.assertFalse(result.execution_allowed)

    def test_ambiguous_legacy_snapshot_never_fabricates_start(self):
        result = self.coordinator.decide(None, legacy_state=True)
        self.assertEqual(result.kind, RecoveryKind.AMBIGUOUS)
        self.assertFalse(result.execution_allowed)
        self.assertIsNone(result.snapshot)

    def test_expired_approval_recovers_state_without_execution(self):
        expired = V3RecoverySnapshot(
            "session-65", "trace-65", "ACTIVE", "auto:calcium", "MAIN",
            True, SafetyState.ALLOW, intent(), approval(expiry=20.0), 1,
        )
        result = self.coordinator.decide(expired, now=20.0)
        self.assertEqual(result.kind, RecoveryKind.RECOVER_EXISTING)
        self.assertFalse(result.execution_allowed)
        self.assertIn("expired", result.reason)

    def test_missing_approval_and_decision_mismatch_are_denied(self):
        missing = self.coordinator.decide(snapshot(approved=False), now=20.0)
        self.assertFalse(missing.execution_allowed)
        mismatched = V3RecoverySnapshot(
            "session-65", "trace-65", "ACTIVE", "auto:calcium", "MAIN",
            True, SafetyState.ALLOW, intent(), approval("other-decision"), 1,
        )
        mismatch = self.coordinator.decide(mismatched, now=20.0)
        self.assertFalse(mismatch.execution_allowed)
        self.assertIn("match", mismatch.reason)

    def test_audit_cursor_preserves_prefix_and_prevents_duplicates(self):
        first = DecisionAuditEvent("event-1", "decision-65", "intent-65", "approval-65", "session-65", 1.0, "v3", "OK", "PROGRAM_SELECTION", "selected")
        trail = DecisionAuditTrail().append(first)
        next_event = DecisionAuditEvent("event-2", "decision-65", "intent-65", "approval-65", "session-65", 2.0, "v3", "OK", "PHASE_DECISION", "main")
        result = AuditContinuityValidator().continue_after_restart(trail, 1, (next_event,))
        self.assertTrue(result.valid)
        self.assertEqual(len(result.trail.events), 2)
        duplicate = AuditContinuityValidator().continue_after_restart(trail, 1, (first,))
        self.assertFalse(duplicate.valid)


if __name__ == "__main__":
    unittest.main()
