"""Phase 11.1 staged configuration ownership tests."""

from datetime import datetime, timezone
from pathlib import Path
import unittest

from application.configuration_model import ConfigurationModel, default_configuration_authority
from application.configuration_ownership import ConfigurationOwnershipCoordinator, ConfigurationOwnershipState, ConfigurationParityState


ROOT = Path(__file__).resolve().parents[1]


class ConfigurationOwnershipTests(unittest.TestCase):
    def setUp(self) -> None:
        self.model = ConfigurationModel.resolve(default_configuration_authority(), [])
        self.v2 = {key: self.model.get(key) for key in self.model.keys()}
        self.coordinator = ConfigurationOwnershipCoordinator()
        self.now = datetime.now(timezone.utc)

    def test_canonical_snapshot_and_provenance(self) -> None:
        view = self.coordinator.publish(trace_id="trace-config", model=self.model, v2_effective=self.v2, now=self.now)
        self.assertEqual(ConfigurationOwnershipState.V3_CANONICAL, view.state)
        self.assertEqual(ConfigurationParityState.EQUAL, view.parity.state)
        self.assertEqual("default", view.provenance["safety.max_voltage_v"])
        self.assertIn("charge.manual.main.voltage_v", view.canonical)
        self.assertIn("strategy.mix.finish_hold_s", view.canonical)
        self.assertIn("containment.off_confirmation_poll_s", view.canonical)
        self.assertIn("transport.telemetry_interval_s", view.canonical)

    def test_v2_parity_difference_is_recorded(self) -> None:
        v2 = dict(self.v2)
        v2["safety.max_voltage_v"] = 17.0
        view = self.coordinator.publish(trace_id="trace-diff", model=self.model, v2_effective=v2, now=self.now)
        self.assertEqual(ConfigurationParityState.DIFFERENT, view.parity.state)
        self.assertEqual(17.0, view.parity.differences["safety.max_voltage_v"]["v2"])
        self.assertEqual((view,), self.coordinator.shadow_evidence)

    def test_rollback_to_v2_view(self) -> None:
        v2 = dict(self.v2)
        v2["transport.ha_timeout_s"] = 20.0
        self.coordinator.publish(trace_id="trace-rb", model=self.model, v2_effective=v2, now=self.now)
        view = self.coordinator.rollback_to_v2(trace_id="trace-rb-2", now=self.now)
        self.assertEqual(ConfigurationOwnershipState.V2_ROLLBACK, view.state)
        self.assertEqual(20.0, self.coordinator.canonical_view()["transport.ha_timeout_s"])
        self.assertEqual(ConfigurationParityState.EQUAL, view.parity.state)

    def test_conflict_detection_remains_in_model(self) -> None:
        from application.configuration_model import ConfigurationConflictError
        with self.assertRaises(ConfigurationConflictError):
            ConfigurationModel.resolve(default_configuration_authority(), ({"safety.max_voltage_v": 18}, {"safety.max_voltage_v": 17}))

    def test_no_execution_path(self) -> None:
        source = (ROOT / "application" / "configuration_ownership.py").read_text(encoding="utf-8").lower()
        for token in ("output_on(", "output_off(", "set_voltage(", "set_current(", "controller.start", "controller.stop", "ha.write", "esp.write"):
            self.assertNotIn(token, source)

    def test_document_declares_configuration_only_scope(self) -> None:
        text = (ROOT / "docs" / "RD6018_CONFIGURATION_OWNERSHIP_MIGRATION.md").read_text(encoding="utf-8")
        for phrase in ("ConfigurationAuthority", "ConfigurationModel", "provenance", "rollback", "runtime and physical ownership"):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
