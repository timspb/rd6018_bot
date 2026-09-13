import unittest

from runtime.diagnostics import BatteryDiagnosticEvidence, DiagnosticAuthority, evaluate_battery_diagnostics
from runtime.charge import ChargeIntent, Measurements
from runtime.output import OutputAction, OutputIntentFactory
from runtime.safety import SafetyContext, SafetyEngine, SafetyLimits
from runtime.telemetry import TelemetrySnapshot


class V3DiagnosticSafetyBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.engine = SafetyEngine(SafetyLimits(17.5, 12.0))
        self.measurements = Measurements(16.5, 2.0, 30.0, 10.0)

    def test_confirmed_cell_fault_becomes_hard_stop(self):
        diagnostic = evaluate_battery_diagnostics(
            BatteryDiagnosticEvidence(True, ("rested_ocv", "independent_cell_check"))
        )
        self.assertEqual(DiagnosticAuthority.HARD_STOP, diagnostic.authority)
        decision = self.engine.evaluate(
            ChargeIntent(16.5, 2.0, "mix"), self.measurements,
            SafetyContext(diagnostic=diagnostic, telemetry_snapshot=TelemetrySnapshot(16.5, 2.0)),
        )
        self.assertFalse(decision.allowed)
        self.assertTrue(decision.shutdown_required)
        self.assertEqual("diagnostic_hard_stop", decision.violations[0].type)
        self.assertEqual(OutputAction.DISABLE, OutputIntentFactory().create(decision).action)

    def test_unconfirmed_evidence_does_not_stop(self):
        diagnostic = evaluate_battery_diagnostics(BatteryDiagnosticEvidence())
        decision = self.engine.evaluate(
            ChargeIntent(16.5, 2.0, "mix"), self.measurements, SafetyContext(diagnostic=diagnostic)
        )
        self.assertTrue(decision.allowed)
        self.assertFalse(decision.shutdown_required)

    def test_confirmed_fault_requires_provenance(self):
        with self.assertRaises(ValueError):
            BatteryDiagnosticEvidence(True)


if __name__ == "__main__":
    unittest.main()
