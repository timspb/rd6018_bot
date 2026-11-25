import types
import unittest

from application.start_event_context import (
    build_start_execution_identity,
    build_start_execution_intent,
)


class StartEventContextMappingTests(unittest.TestCase):
    def test_identity_preserves_trace_and_session_with_fallback_ids(self):
        traced = build_start_execution_identity(
            event_context=types.SimpleNamespace(trace_id="trace-7"),
            recovery_context={"session_id": "session-9"},
            battery_id="battery-2",
            mode="AUTO_START",
        )
        self.assertEqual((traced.session_id, traced.trace_id), ("session-9", "trace-7"))

        fallback = build_start_execution_identity(
            event_context=None,
            recovery_context={},
            battery_id="battery-2",
            mode="AUTO_START",
        )
        self.assertEqual(fallback.session_id, "auto_start:battery-2")
        self.assertEqual(fallback.trace_id, "auto_start:auto_start:battery-2")

    def test_execution_intent_is_data_only_with_start_safety_metadata(self):
        identity = types.SimpleNamespace(session_id="s", trace_id="t")
        intent = build_start_execution_intent(
            voltage_v="14.4",
            current_a="6.2",
            mode="AUTO_START",
            identity=identity,
            limits_reference="recipe_envelope",
        )
        self.assertEqual((intent.requested_voltage_v, intent.requested_current_a), (14.4, 6.2))
        self.assertEqual(intent.requested_mode, "AUTO_START")
        self.assertEqual(intent.source_decision_id, "auto_start:t")
        self.assertEqual(intent.safety_context.telemetry_state, "FRESH")
        self.assertEqual(intent.safety_context.lease_state, "V2_PHYSICAL_OWNER")
        self.assertEqual(intent.safety_context.verification_state, "REQUIRED")
        self.assertEqual(intent.safety_context.limits_reference, "recipe_envelope")


if __name__ == "__main__":
    unittest.main()
