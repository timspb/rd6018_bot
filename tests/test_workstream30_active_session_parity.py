import ast
import unittest
from pathlib import Path

from application.active_session_parity import ActiveSessionIdentityStatus, ActiveSessionParityObserver, ActiveSessionParityStatus


class Workstream30ActiveSessionParityTests(unittest.TestCase):
    def setUp(self):
        self.observer = ActiveSessionParityObserver()

    def test_active_legacy_session_is_valid_input_without_identity(self):
        observation = self.observer.ingest(
            persisted={"state": "active", "stage": "mix", "request": {"battery_id": "Baic72"}},
            telemetry={"voltage": 17.14, "current": 3.48, "power": 59.81},
            rd={"phase": "mix"}, esphome={"output": True}, ha={"available": True},
        )
        self.assertEqual(ActiveSessionIdentityStatus.LEGACY_NO_IDENTITY, observation.identity_status)
        self.assertEqual(("Baic72", "mix", "active"), (observation.profile, observation.phase, observation.state))
        self.assertEqual("HIGH", observation.confidence)

    def test_v3_reconstructs_mix_and_matches_v2(self):
        observation = self.observer.ingest(persisted={"state": "active", "stage": "mix", "request": {"battery_id": "Baic72"}}, telemetry={"voltage": 17.14})
        evidence = self.observer.compare(observation, v2_state={"profile": "Baic72", "phase": "mix", "state": "active"}, v3_state={"profile": "Baic72", "phase": "mix", "state": "active"})
        self.assertEqual(ActiveSessionParityStatus.MATCH, evidence.comparison)
        self.assertFalse(evidence.fake_start_emitted)

    def test_missing_domain_field_is_unknown(self):
        observation = self.observer.ingest(persisted={"state": "active"}, telemetry={})
        evidence = self.observer.compare(observation, v2_state={"state": "active"}, v3_state={"state": "active"})
        self.assertEqual(ActiveSessionParityStatus.UNKNOWN, evidence.comparison)

    def test_ui_is_current_session_only(self):
        observation = self.observer.ingest(persisted={"state": "active", "stage": "mix"}, telemetry={"voltage": 17.14, "current": 3.48})
        evidence = self.observer.compare(observation, v2_state={"profile": "Baic72", "phase": "mix", "state": "active"}, v3_state={"profile": "Baic72", "phase": "mix", "state": "active"})
        self.assertTrue(evidence.ui_current_session_only)
        self.assertFalse(evidence.fake_start_emitted)

    def test_no_physical_calls(self):
        source = (Path(__file__).resolve().parents[1] / "application" / "active_session_parity.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        self.assertFalse(imports & {"aiohttp", "aioesphomeapi", "paramiko", "serial", "requests"})
        for token in ("output_on", "output_off", "turn_on", "turn_off", "lease_renew", "controller.start", "controller.stop"):
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
