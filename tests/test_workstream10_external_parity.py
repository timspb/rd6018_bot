import ast
import unittest
from pathlib import Path

from v3_core.external_parity import (
    ExternalReadbackStatus,
    ExternalReadbackValidationModel,
    IntegrationStatus,
    LeaseIntegrationScenario,
    TelemetryCandidate,
    TelemetryParityValidationModel,
    external_failure_matrix,
    esphome_parity_model,
    ha_integration_parity_model,
    lease_integration_parity_report,
)


ROOT = Path(__file__).resolve().parents[1]


class Workstream10ExternalParityTests(unittest.TestCase):
    def test_esphome_mapping_is_explicit_and_not_live(self):
        model = esphome_parity_model()
        self.assertEqual("ESPHome/edge dead-man", model.owner)
        self.assertGreaterEqual(len(model.mappings), 5)
        self.assertTrue(all(item.status is not IntegrationStatus.MATCHED for item in model.mappings))
        self.assertTrue(all(item.source and item.target and item.verification for item in model.mappings))

    def test_ha_role_is_not_safety_or_physical_owner(self):
        model = ha_integration_parity_model()
        self.assertIn("presentation", model.notification_role)
        self.assertTrue(any(item.startswith("sensor.") for item in model.telemetry_entities))
        self.assertIn("does not", model.safety_owner)
        self.assertIn("V2", model.physical_owner)
        self.assertTrue(model.telemetry_entities and model.control_entities)

    def test_lease_scenarios_preserve_current_owner(self):
        report = lease_integration_parity_report()
        self.assertEqual("ESPHome/edge dead-man", report.current_owner)
        self.assertEqual(900.0, report.timeout_s)
        self.assertEqual(set(LeaseIntegrationScenario), {case.scenario for case in report.cases})

    def test_telemetry_arbitration_and_conflict_provenance(self):
        model = TelemetryParityValidationModel()
        esp = TelemetryCandidate("ESP_DIRECT", {"voltage": 14.7}, 1, 1.0)
        ha = TelemetryCandidate("HA", {"voltage": 14.5}, 1, 1.0)
        result = model.arbitrate(esp, ha)
        self.assertEqual("ESP_DIRECT", result.selected_source)
        self.assertTrue(result.conflicting)
        stale = model.arbitrate(None, TelemetryCandidate("HA", {}, 30, 1.0), TelemetryCandidate("LAST", {}, 100, 0.2))
        self.assertEqual("LAST_KNOWN", stale.selected_source)

    def test_readback_never_equates_acceptance_with_physical_success(self):
        model = ExternalReadbackValidationModel()
        self.assertEqual(ExternalReadbackStatus.VERIFIED, model.verify(command_accepted=True, physical_changed=True, telemetry_confirms=True))
        self.assertEqual(ExternalReadbackStatus.UNVERIFIED, model.verify(command_accepted=True, physical_changed=None, telemetry_confirms=None))
        self.assertEqual(ExternalReadbackStatus.TIMEOUT, model.verify(command_accepted=True, physical_changed=None, telemetry_confirms=None, timed_out=True))
        self.assertEqual(ExternalReadbackStatus.MISMATCH, model.verify(command_accepted=True, physical_changed=True, telemetry_confirms=False))

    def test_failure_matrix_covers_external_categories(self):
        matrix = external_failure_matrix()
        self.assertGreaterEqual(len(matrix), 8)
        self.assertTrue({"transport", "ESPHome", "HA", "lease", "telemetry", "readback"} <= {item.category for item in matrix})
        self.assertTrue(all(item.detection and item.decision and item.containment and item.verification and item.recovery for item in matrix))

    def test_external_parity_module_has_no_clients_or_physical_calls(self):
        path = ROOT / "v3_core" / "external_parity.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        self.assertTrue(all(not any(token in item for token in ("hass", "esphome", "runtime", "serial", "gpio")) for item in imports))
        text = path.read_text(encoding="utf-8")
        for token in ("turn_on(", "turn_off(", "set_voltage(", "set_current("):
            self.assertNotIn(token, text)


if __name__ == "__main__":
    unittest.main()
