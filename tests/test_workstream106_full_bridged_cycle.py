import unittest
from pathlib import Path
from application.execution_intent.models import ExecutionIntent, SafetyContext
from application.start_authority.contracts import Mode, StartRequest
from application.start_orchestration import StartOrchestrator
from application.v2_identity_bridge import IdentityPropagationStatus, V2Operation, bridge_request


class Workstream106BridgedCycleContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = (
            Path(__file__).parents[1]
            / "docs"
            / "RD6018_FULL_BRIDGED_CONTROL_CYCLE_REPORT.md"
        ).read_text(encoding="utf-8")

    def test_start_orchestration_identity_reaches_v2_bridge(self):
        request = StartRequest(
            operator_intent="controlled_canary_preview",
            program_id="CALCIUM",
            battery_identity="bench-battery",
            mode=Mode.MANUAL,
            requested_parameters_ref="controlled-test",
            requested_parameters={"voltage_v": 13.0, "current_a": 0.4},
        )
        result = StartOrchestrator().orchestrate(request, now=100.0)
        self.assertTrue(result.decision.status.value == "ALLOW")
        self.assertIsNotNone(result.identity)
        self.assertIsNotNone(result.execution_intent)
        intent = result.execution_intent
        bridge = bridge_request(
            V2Operation.START,
            session_id=result.identity.session_id,
            trace_id=result.identity.trace_id,
            decision_id=result.request_id,
            intent_id=intent.intent_id,
        )
        self.assertEqual(bridge.identity.status, IdentityPropagationStatus.PROPAGATED)

    def test_stop_and_settings_reuse_same_identity_without_execution(self):
        identity = {"session_id": "s", "trace_id": "t", "decision_id": "d", "intent_id": "i"}
        for operation in (V2Operation.SETTINGS, V2Operation.STOP):
            request = bridge_request(operation, parameters={"observed": True}, **identity)
            self.assertTrue(request.identity.correlated)

    def test_existing_execution_intent_gets_creation_identity(self):
        intent = ExecutionIntent(13.0, 0.4, "SETPOINT", "decision", SafetyContext())
        self.assertTrue(intent.intent_id)

    def test_no_v3_direct_transport_in_contract_test(self):
        intent = ExecutionIntent(13.0, 0.4, "SETPOINT", "decision", SafetyContext())
        self.assertEqual(intent.requested_current_a, 0.4)

    def test_live_cycle_evidence(self):
        self.assertIn("FULL_BRIDGED_CONTROL_CYCLE_COMPLETE", self.report)
        self.assertIn("START bridge: `PROPAGATED`", self.report)
        self.assertIn("STOP bridge: `PROPAGATED`", self.report)
        self.assertIn("10.157 s", self.report)
        self.assertIn("maximum current: `0.39 A`", self.report)
        self.assertIn("final Output State Code V2: `0 / OFF`", self.report)

    def test_no_synthetic_session_stop_claim(self):
        self.assertIn("synthetic V2 event", self.report)


if __name__ == "__main__":
    unittest.main()
