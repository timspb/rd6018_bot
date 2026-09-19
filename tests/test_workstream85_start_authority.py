import unittest

from application.start_authority import (
    InitialState, Mode, PhysicalVerification, SessionStarted,
    StartDecision, StartDecisionStatus, StartIdentity, StartRequest,
)


class StartAuthorityContractTests(unittest.TestCase):
    def test_request_is_data_only_and_validated(self):
        request = StartRequest("operator-intent", "CALCIUM", "Baic72", Mode.MANUAL, "config:manual:1", {"voltage_v": 13.0})
        self.assertEqual(request.mode, Mode.MANUAL)
        with self.assertRaises(TypeError):
            StartRequest("intent", "CALCIUM", "Baic72", "MANUAL", "ref")

    def test_identity_has_independent_session_trace_and_graph_ids(self):
        identity = StartIdentity.create(created_at=100.0)
        self.assertEqual(identity.created_at, 100.0)
        self.assertEqual(len({identity.session_id, identity.trace_id, identity.graph_session_id}), 3)

    def test_session_started_is_lifecycle_contract_not_execution(self):
        identity = StartIdentity.create(created_at=100.0)
        event = SessionStarted(identity, 101.0, "CALCIUM", InitialState.ARMING)
        decision = StartDecision(StartDecisionStatus.ALLOW, "validated start intent", identity, event)
        self.assertEqual(decision.lifecycle_event.identity, identity)
        self.assertEqual(event.initial_state, InitialState.ARMING)

    def test_denied_and_ambiguous_never_emit_start(self):
        for status in (StartDecisionStatus.DENY, StartDecisionStatus.AMBIGUOUS):
            decision = StartDecision(status, "missing evidence")
            self.assertIsNone(decision.lifecycle_event)
            self.assertIsNone(decision.identity)

    def test_physical_verification_is_separate_data(self):
        verification = PhysicalVerification(True, True, 102.0, "readback confirmed")
        self.assertTrue(verification.verified)
        self.assertTrue(verification.output_on)

    def test_no_hardware_or_v2_dependencies(self):
        for module_name in ("application.start_authority", "application.start_authority.contracts"):
            module = __import__(module_name, fromlist=["*"])
            with open(module.__file__, encoding="utf-8") as handle:
                source = handle.read()
            for forbidden in ("HassClient", "ESPHome", "Modbus", "ChargeController", "turn_on", "turn_off"):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
