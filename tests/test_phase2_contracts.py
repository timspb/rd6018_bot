"""Read-only tests for Phase 2 data contracts."""

from __future__ import annotations

import json
import unittest
from dataclasses import FrozenInstanceError

from application.charge_event import ChargeEvent
from application.safety_state import SafetyState


class Phase2ContractTests(unittest.TestCase):
    def make_event(self) -> ChargeEvent:
        return ChargeEvent.new(
            trace_id="trace-1",
            session_id="session-1",
            source="test",
            event_type="phase_transition",
            severity="info",
            timestamp=123.0,
            profile="AGM",
            phase="main",
            measurements={"voltage": 14.8, "nested": {"current": 1.0}},
            decision={"allowed": True},
            actuator_effect={"kind": "none"},
        )

    def test_charge_event_is_immutable_and_deeply_frozen(self):
        event = self.make_event()
        with self.assertRaises(FrozenInstanceError):
            event.source = "other"  # type: ignore[misc]
        with self.assertRaises(TypeError):
            event.measurements["voltage"] = 12.0  # type: ignore[index]
        self.assertEqual(event.measurements["nested"]["current"], 1.0)

    def test_charge_event_schema_validation(self):
        with self.assertRaises(ValueError):
            ChargeEvent.new(
                trace_id="",
                session_id="session-1",
                source="test",
                event_type="x",
                severity="info",
            )
        with self.assertRaises(ValueError):
            ChargeEvent.new(
                trace_id="trace-1",
                session_id="session-1",
                source="test",
                event_type="x",
                severity="info",
                timestamp=float("nan"),
            )

    def test_charge_event_serialization_round_trip(self):
        event = self.make_event()
        encoded = json.dumps(event.to_dict(), sort_keys=True)
        restored = ChargeEvent.from_dict(json.loads(encoded))
        self.assertEqual(restored, event)
        self.assertEqual(restored.to_dict(), event.to_dict())

    def test_safety_state_vocabulary_is_data_only(self):
        self.assertEqual(
            {state.value for state in SafetyState},
            {
                "normal",
                "degraded",
                "containment",
                "off_confirmed",
                "off_unconfirmed",
                "latched",
            },
        )


if __name__ == "__main__":
    unittest.main()
