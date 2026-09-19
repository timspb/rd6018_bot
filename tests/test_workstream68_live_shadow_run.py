"""WS68 validation over a captured read-only live observation.

The fixture is a sanitized observation: it contains measurements and state,
never credentials or command surfaces. The test only runs the parity engine.
"""

import unittest
from dataclasses import dataclass

from application.charge_engine.models import TelemetrySnapshot
from application.shadow_decision_parity import (
    ShadowDecisionInput,
    ShadowDecisionParityEngine,
    ShadowDecisionView,
    ShadowParityStatus,
)


@dataclass(frozen=True)
class LiveObservationEvidence:
    observed_at: str
    source: str
    confidence: str
    output_on: bool
    profile: str
    phase: str
    voltage_v: float
    current_a: float
    power_w: float
    temperature_c: float
    safety_result: str
    session_identity: str


LIVE = LiveObservationEvidence(
    observed_at="2026-09-15T11:03:54Z",
    source="HA102 + node101 V2 persisted state",
    confidence="PARTIAL_LEGACY_IDENTITY_UNKNOWN",
    output_on=True,
    profile="Baic72",
    phase="MIX",
    voltage_v=17.10,
    current_a=3.49,
    power_w=59.67,
    temperature_c=42.0,
    safety_result="ALLOW",
    session_identity="UNKNOWN_LEGACY_NO_IDENTITY",
)


def shadow_input(telemetry=True):
    return ShadowDecisionInput(
        TelemetrySnapshot(1789463034.0, 17.10, 3.49, 42.0, fresh=telemetry),
        LIVE.profile,
        LIVE.phase,
        "manual:Baic72",
        "ACTIVE",
        "",
        1789463034.0,
    )


def decision_view():
    return ShadowDecisionView(
        "manual:Baic72",
        "MIX",
        17.5,
        3.5,
        "ALLOW",
        (("voltage", 17.5), ("current", 3.5)),
    )


class LiveV2V3ShadowRunTests(unittest.TestCase):
    def setUp(self):
        self.engine = ShadowDecisionParityEngine()

    def test_captured_live_observation_has_required_read_only_fields(self):
        self.assertTrue(LIVE.output_on)
        self.assertEqual((LIVE.profile, LIVE.phase), ("Baic72", "MIX"))
        self.assertGreater(LIVE.voltage_v, 0)
        self.assertGreater(LIVE.current_a, 0)
        self.assertEqual(LIVE.safety_result, "ALLOW")
        self.assertIn("UNKNOWN", LIVE.session_identity)

    def test_live_v2_and_v3_views_match_for_observed_fields(self):
        result = self.engine.compare(shadow_input(), decision_view(), decision_view())
        self.assertEqual(result.status, ShadowParityStatus.MATCH)
        self.assertEqual(result.divergences, ())

    def test_missing_live_telemetry_is_unknown_not_a_command(self):
        result = self.engine.compare(shadow_input(False), decision_view(), decision_view())
        self.assertEqual(result.status, ShadowParityStatus.UNKNOWN)

    def test_live_safety_or_target_divergence_is_report_only(self):
        different = ShadowDecisionView(
            "manual:Baic72", "MIX", 17.5, 3.0, "DENY",
            (("voltage", 17.5), ("current", 3.0)),
        )
        result = self.engine.compare(shadow_input(), decision_view(), different)
        self.assertEqual(result.status, ShadowParityStatus.DIVERGENCE)
        self.assertEqual({item.field for item in result.divergences}, {"target_current_a", "safety_result", "execution_intent"})

    def test_observer_path_has_no_write_or_control_surface(self):
        import application.shadow_decision_parity as module
        with open(module.__file__, encoding="utf-8") as handle:
            source = handle.read()
        for forbidden in ("call_service", "requests.post", "turn_on", "turn_off", "lease_renew", "PhysicalExecution"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
