import unittest
from pathlib import Path

from application.v2_identity_bridge import (
    IdentityPropagationStatus,
    V2Operation,
    bridge_request,
)


class Workstream105IdentityBridgeTests(unittest.TestCase):
    def test_full_identity_propagates_for_start(self):
        request = bridge_request(
            V2Operation.START,
            session_id="session-1",
            trace_id="trace-1",
            decision_id="decision-1",
            intent_id="intent-1",
        )

        self.assertEqual(request.identity.status, IdentityPropagationStatus.PROPAGATED)
        self.assertTrue(request.identity.correlated)
        self.assertEqual(request.operation, V2Operation.START)

    def test_same_contract_covers_stop_and_settings(self):
        for operation in (V2Operation.STOP, V2Operation.SETTINGS):
            request = bridge_request(
                operation,
                parameters={"value": "observed"},
                session_id="session-1",
                trace_id="trace-1",
                decision_id="decision-1",
                intent_id="intent-1",
            )
            self.assertEqual(request.operation, operation)
            self.assertTrue(request.identity.correlated)

    def test_missing_identity_uses_legacy_fallback_without_generation(self):
        request = bridge_request(V2Operation.START)

        self.assertEqual(
            request.identity.status,
            IdentityPropagationStatus.UNKNOWN_LEGACY_NO_IDENTITY,
        )
        self.assertIsNone(request.identity.session_id)
        self.assertIsNone(request.identity.trace_id)
        self.assertIsNone(request.identity.decision_id)
        self.assertIsNone(request.identity.intent_id)

    def test_partial_identity_is_blocked(self):
        request = bridge_request(V2Operation.STOP, session_id="session-1", trace_id="trace-1")

        self.assertEqual(
            request.identity.status,
            IdentityPropagationStatus.BLOCKED_PARTIAL_IDENTITY,
        )
        self.assertFalse(request.identity.correlated)

    def test_parameters_are_metadata_only(self):
        request = bridge_request(V2Operation.SETTINGS, parameters={"voltage": 13.0})

        self.assertEqual(request.parameters, {"voltage": 13.0})
        self.assertFalse(request.identity.correlated)

    def test_bridge_has_no_transport_or_hardware_dependency(self):
        import application.v2_identity_bridge as bridge

        source = Path(bridge.__file__).read_text(encoding="utf-8")
        for forbidden in ("hass", "esphome", "modbus", "turn_on(", "turn_off(", "set_voltage(", "set_current("):
            self.assertNotIn(forbidden, source.lower())


if __name__ == "__main__":
    unittest.main()
