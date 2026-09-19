import unittest

from application.decision_audit import (
    DecisionAuditEvent,
    DecisionAuditStep,
    DecisionAuditTrail,
    REQUIRED_TRACE_STEPS,
)


def event(number, step, result="OK", reason=None, *, approval_id="approval-64", intent_id="intent-64"):
    return DecisionAuditEvent(
        event_id=f"event-{number}",
        decision_id="decision-64",
        intent_id=intent_id,
        approval_id=approval_id,
        session_id="session-64",
        timestamp=float(number),
        actor="v3-shadow",
        result=result,
        step=step,
        reason=reason or f"reason for {step}",
    )


def full_trail(*, result="VERIFIED"):
    trail = DecisionAuditTrail()
    for number, step in enumerate(REQUIRED_TRACE_STEPS, 1):
        trail = trail.append(event(number, step, result=result if step == "EXECUTION_OUTCOME" else "OK"))
    return trail


class DecisionAuditTrailTests(unittest.TestCase):
    def test_full_trace_is_replayable_and_explainable(self):
        replay = full_trail().replay()
        self.assertTrue(replay.complete)
        self.assertEqual(replay.missing_steps, ())
        self.assertEqual(len(replay.events), 6)
        self.assertIn(("PROGRAM_SELECTION", "reason for PROGRAM_SELECTION"), replay.explanations)
        self.assertIn(("APPROVAL", "reason for APPROVAL"), replay.explanations)

    def test_denied_path_is_a_complete_trace_without_physical_claim(self):
        trail = full_trail(result="DENIED")
        replay = trail.replay()
        self.assertTrue(replay.complete)
        self.assertEqual(replay.events[-1].result, "DENIED")
        self.assertEqual(replay.events[-1].step, DecisionAuditStep.EXECUTION_OUTCOME)

    def test_expired_approval_is_explained_without_fake_approval(self):
        trail = DecisionAuditTrail()
        for number, step in enumerate((
            "PROGRAM_SELECTION", "PHASE_DECISION", "SAFETY_DECISION", "INTENT_CREATION",
        ), 1):
            trail = trail.append(event(number, step, approval_id=""))
        trail = trail.append(event(5, "APPROVAL", "EXPIRED", "approval expired", approval_id="approval-64"))
        replay = trail.replay()
        self.assertFalse(replay.complete)
        self.assertIn("EXECUTION_OUTCOME", replay.missing_steps)
        self.assertIn(("APPROVAL", "approval expired"), replay.explanations)

    def test_missing_event_is_reported(self):
        trail = DecisionAuditTrail().append(event(1, "PROGRAM_SELECTION"))
        replay = trail.replay()
        self.assertFalse(replay.complete)
        self.assertEqual(replay.missing_steps, REQUIRED_TRACE_STEPS[1:])

    def test_append_only_and_immutable(self):
        first = DecisionAuditTrail().append(event(1, "PROGRAM_SELECTION"))
        second = first.append(event(2, "PHASE_DECISION"))
        self.assertEqual(len(first.events), 1)
        self.assertEqual(len(second.events), 2)
        with self.assertRaises(ValueError):
            first.append(event(1, "PHASE_DECISION"))
        with self.assertRaises(ValueError):
            second.append(event(1.5, "SAFETY_DECISION", reason="out of order"))
        with self.assertRaises(ValueError):
            second.append(event(4, "SAFETY_DECISION", reason="mixed", intent_id="other"))

    def test_identity_and_timestamp_integrity(self):
        with self.assertRaises(ValueError):
            DecisionAuditEvent("", "decision", "", "", "session", 1.0, "actor", "OK", "APPROVAL", "why")
        with self.assertRaises(ValueError):
            DecisionAuditTrail().append(event(1, "PROGRAM_SELECTION")).append(
                event(0, "PHASE_DECISION", reason="earlier")
            )


if __name__ == "__main__":
    unittest.main()
