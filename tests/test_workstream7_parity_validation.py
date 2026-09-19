import ast
import unittest
from pathlib import Path

from v3_core.contracts import SafetyAction
from v3_core.parity_validation import (
    LeaseScenario,
    ParityStatus,
    RestartScenario,
    TelemetryState,
    TransportParityModel,
    TransportParityState,
    bench_validation_matrix,
    lease_parity_report,
    restart_recovery_validation_model,
    safety_trigger_ownership_map,
    telemetry_safety_decision,
)


ROOT = Path(__file__).resolve().parents[1]


class Workstream7ParityTests(unittest.TestCase):
    def test_safety_trigger_map_has_one_logical_owner_and_traceable_chain(self):
        records = safety_trigger_ownership_map()
        self.assertEqual(8, len(records))
        self.assertEqual({"V3 Safety Domain"}, {record.decision_owner for record in records})
        self.assertTrue(all(record.execution_path and record.verification and record.status is not ParityStatus.VALIDATED for record in records))

    def test_lease_cases_preserve_current_owner_and_duplicate_rejection(self):
        report = lease_parity_report()
        self.assertEqual("ESPHome/edge dead-man", report.current_owner)
        self.assertEqual(900.0, report.ttl_s)
        self.assertEqual({LeaseScenario.VALID, LeaseScenario.EXPIRED, LeaseScenario.RENEWAL_FAILURE, LeaseScenario.DUPLICATE_OWNER, LeaseScenario.RESTART}, {case.scenario for case in report.cases})
        duplicate = next(case for case in report.cases if case.scenario is LeaseScenario.DUPLICATE_OWNER)
        self.assertEqual(ParityStatus.BLOCKED, duplicate.status)

    def test_transport_states_never_assume_success_without_verification(self):
        model = TransportParityModel()
        self.assertTrue(model.evaluate(TransportParityState.AVAILABLE, observed=True, expected=True).verified)
        for state in (TransportParityState.TIMEOUT, TransportParityState.UNAVAILABLE, TransportParityState.REJECTED, TransportParityState.DELAYED, TransportParityState.CORRUPTED_RESPONSE):
            self.assertFalse(model.evaluate(state, observed=True, expected=True).verified)

    def test_telemetry_failures_contain(self):
        self.assertEqual(SafetyAction.ALLOW, telemetry_safety_decision(TelemetryState.FRESH, "fresh").action)
        for state in (TelemetryState.STALE, TelemetryState.UNAVAILABLE, TelemetryState.CONFLICTING):
            self.assertEqual(SafetyAction.CONTAIN, telemetry_safety_decision(state, state.value).action)

    def test_restart_model_never_allows_automatic_resume(self):
        cases = restart_recovery_validation_model()
        self.assertEqual(set(RestartScenario), {case.scenario for case in cases})
        self.assertTrue(all("no automatic" in case.expected_behavior for case in cases))

    def test_bench_matrix_is_complete_and_not_executed(self):
        matrix = bench_validation_matrix()
        self.assertGreaterEqual(len(matrix), 7)
        self.assertTrue(all(item.setup and item.expected and item.pass_criteria for item in matrix))

    def test_parity_module_has_no_physical_imports_or_commands(self):
        path = ROOT / "v3_core" / "parity_validation.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        self.assertTrue(all(not any(token in item for token in ("hass", "esphome", "runtime", "serial", "gpio")) for item in imports))


if __name__ == "__main__":
    unittest.main()
