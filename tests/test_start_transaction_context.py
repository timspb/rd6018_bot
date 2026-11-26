import unittest
from types import SimpleNamespace

from application.start_transaction_service import (
    build_start_execution_intent,
    execution_identity_for_start,
)


class StartTransactionContextTests(unittest.TestCase):
    def test_existing_controller_session_and_event_trace_are_preserved(self):
        identity = execution_identity_for_start(
            controller_context={"session_id": "session-42"},
            event_context=SimpleNamespace(trace_id="trace-17"),
            pending_battery_id="battery-1",
            mode="AUTO_START",
        )
        self.assertEqual(identity.session_id, "session-42")
        self.assertEqual(identity.trace_id, "trace-17")

    def test_missing_context_uses_exact_legacy_fallbacks(self):
        identity = execution_identity_for_start(
            controller_context=None,
            event_context=None,
            pending_battery_id="battery-1",
            mode="AUTO_START",
        )
        self.assertEqual(identity.session_id, "auto_start:battery-1")
        self.assertEqual(identity.trace_id, "auto_start:auto_start:battery-1")

    def test_explicit_none_battery_id_preserves_legacy_stringification(self):
        identity = execution_identity_for_start(
            controller_context={},
            event_context=None,
            pending_battery_id=None,
            mode="AUTO_START",
        )
        self.assertEqual(identity.session_id, "auto_start:None")

    def test_execution_intent_preserves_existing_safety_contract(self):
        identity = SimpleNamespace(trace_id="trace-99")
        intent = build_start_execution_intent(
            voltage_v=14.8,
            current_a=7.2,
            mode="AUTO_START",
            identity=identity,
            limits_reference="recipe_envelope",
        )
        self.assertEqual(intent.requested_voltage_v, 14.8)
        self.assertEqual(intent.requested_current_a, 7.2)
        self.assertEqual(intent.requested_mode, "AUTO_START")
        self.assertEqual(intent.source_decision_id, "auto_start:trace-99")
        self.assertEqual(intent.safety_context.telemetry_state, "FRESH")
        self.assertEqual(intent.safety_context.lease_state, "V2_PHYSICAL_OWNER")
        self.assertEqual(intent.safety_context.verification_state, "REQUIRED")
        self.assertEqual(intent.safety_context.limits_reference, "recipe_envelope")


if __name__ == "__main__":
    unittest.main()
