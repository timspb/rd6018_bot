import unittest

from application.start_authority.contracts import Mode, StartDecisionStatus, StartRequest
from application.start_orchestration import GateResult, StartOrchestrator


def request():
    return StartRequest(
        operator_intent="dry-run start",
        program_id="TEST_PROGRAM",
        battery_identity="BATTERY-1",
        mode=Mode.MANUAL,
        requested_parameters_ref="test-config",
        requested_parameters={"voltage_v": 13.0, "current_a": 0.4},
    )


class Workstream86Tests(unittest.TestCase):
    def test_successful_dry_run_creates_contracts_only(self):
        result = StartOrchestrator().orchestrate(request(), now=100.0)
        self.assertEqual(result.decision.status, StartDecisionStatus.ALLOW)
        self.assertIsNotNone(result.identity)
        self.assertIsNotNone(result.lifecycle_event)
        self.assertIsNotNone(result.execution_intent)
        self.assertIsNone(result.blocked_reason)
        self.assertFalse(result.physical_request_created)

    def test_safety_denied(self):
        result = StartOrchestrator(
            safety_gate=lambda _request, _intent: GateResult(False, "safety denied")
        ).orchestrate(request(), now=100.0)
        self.assertEqual(result.blocked_reason, "safety denied")
        self.assertIsNotNone(result.execution_intent)
        self.assertFalse(result.physical_request_created)

    def test_approval_denied(self):
        result = StartOrchestrator(
            approval_gate=lambda _request, _intent: GateResult(False, "approval denied")
        ).orchestrate(request(), now=100.0)
        self.assertEqual(result.blocked_reason, "approval denied")
        self.assertFalse(result.physical_request_created)

    def test_ambiguous_start_has_no_identity_or_lifecycle(self):
        class AmbiguousAuthority:
            def decide(self, _request, *, now):
                from application.start_authority.contracts import StartDecision
                return StartDecision(StartDecisionStatus.AMBIGUOUS, "identity cannot be established")

        result = StartOrchestrator(authority=AmbiguousAuthority()).orchestrate(request(), now=100.0)
        self.assertEqual(result.decision.status, StartDecisionStatus.AMBIGUOUS)
        self.assertIsNone(result.identity)
        self.assertIsNone(result.lifecycle_event)
        self.assertIsNone(result.execution_intent)

    def test_no_physical_side_effect(self):
        called = []
        result = StartOrchestrator().orchestrate(request(), now=100.0)
        self.assertEqual(called, [])
        self.assertFalse(result.physical_request_created)


if __name__ == "__main__":
    unittest.main()
